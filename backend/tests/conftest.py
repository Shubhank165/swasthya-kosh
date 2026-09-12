"""Shared fixtures.

The suite runs against SQLite with the schema created from the ORM metadata, so
it needs no database container and no migration step. `tests/integration/`
additionally runs the migration itself, because "the metadata is right" and "the
migration produces the metadata" are two different claims.

Time and identifiers are frozen and sequential throughout. A test that passes
because `uuid4` happened to sort a certain way is a test that fails on a
Thursday.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.content import ClinicalContent, load_clinical_content
from app.core.ids import SequentialIdFactory
from app.db.tenancy import tenant_scope
from app.events.bus import InProcessBus
from app.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
FIXTURES = Path(__file__).parent / "fixtures"

HOSPITAL_ID = "aiia-delhi"
OTHER_HOSPITAL_ID = "test-other"

#: Fixed instant for every test. Reports are golden-file compared, so the clock
#: has to be the same on every machine and in CI.
FROZEN_NOW = datetime(2026, 9, 3, 10, 21, 5, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Local settings: mocks everywhere, storage under the test's tmp dir."""
    return Settings(
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        clinical_content_dir=REPO_ROOT / "clinical",
        document_storage_dir=tmp_path / "uploads",
        ocr_fixtures_dir=FIXTURES / "ocr",
        ocr_provider="mock",
        repair_provider="mock",
        abha_provider="mock",
        storage_backend="local",
        demo_mode=False,
        log_json=False,
        kiosk_tokens={"test-kiosk-token": HOSPITAL_ID},
        # Not a secret — this is a test pepper. Its presence is what matters:
        # `phone_ref()` refuses to run without one rather than falling back to a
        # plain digest, so every patient-app test would fail closed without it.
        patient_ref_pepper="test-pepper-not-a-secret",
    )


@pytest.fixture(scope="session")
def content() -> ClinicalContent:
    """The real clinical content. Loaded once — it is read-only."""
    return load_clinical_content(
        Settings(clinical_content_dir=REPO_ROOT / "clinical")
    )


@pytest.fixture
def clock() -> FrozenClock:
    """A clock that advances one second per read.

    Advancing rather than standing still: two facts recorded in the same test
    should not share a timestamp, or an ordering bug hides.
    """
    return FrozenClock(start=FROZEN_NOW, step=timedelta(seconds=1))


@pytest.fixture
def still_clock() -> FrozenClock:
    """A clock that does not move. For byte-identical golden files."""
    return FrozenClock(start=FROZEN_NOW)


@pytest.fixture
def ids() -> SequentialIdFactory:
    return SequentialIdFactory()


@pytest.fixture
def bus() -> InProcessBus:
    published = InProcessBus()
    published.record_history(True)
    return published


@pytest.fixture
async def engine() -> AsyncIterator[Any]:
    """An in-memory SQLite engine with the schema created."""
    created = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with created.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield created
    await created.dispose()


@pytest.fixture
async def session(engine: Any) -> AsyncIterator[AsyncSession]:
    """One session, inside the seeded hospital's tenant scope."""
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as opened:
        await _create_hospitals(opened)
        with tenant_scope(HOSPITAL_ID):
            yield opened
        await opened.rollback()


async def _create_hospitals(opened: AsyncSession) -> None:
    from app.repositories.patients import HospitalRepository

    repository = HospitalRepository(opened)
    await repository.create(
        hospital_id=HOSPITAL_ID,
        display_name="All India Institute of Ayurveda",
        departments=["kayachikitsa", "panchakarma", "general"],
        default_language="hi",
    )
    await repository.create(
        hospital_id=OTHER_HOSPITAL_ID,
        display_name="Another Hospital",
        departments=["general"],
    )
    await opened.commit()


@pytest.fixture
def unscoped_session_factory(engine: Any) -> Any:
    """Session factory with no tenant scope. For the tenancy tests."""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# --- payload fixtures --------------------------------------------------------


def load_kiosk_fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / "kiosk" / name).open(encoding="utf-8") as handle:
        loaded: dict[str, Any] = json.load(handle)
    return loaded


@pytest.fixture
def kiosk_payload() -> dict[str, Any]:
    """The reference 0.1 payload. A complete Hindi intake."""
    return load_kiosk_fixture("0.1.json")


@pytest.fixture
def ocr_images() -> dict[str, bytes]:
    """The fixture image bytes, keyed by name."""
    import sys

    sys.path.insert(0, str(BACKEND_ROOT))
    from tests.fixtures.build_ocr_fixtures import IMAGES

    return dict(IMAGES)


# --- assembled services ------------------------------------------------------


@pytest.fixture
def providers(settings: Settings) -> Any:
    from app.adapters.registry import build_providers

    return build_providers(settings)


@pytest.fixture
def ingest_service(
    session: AsyncSession,
    bus: InProcessBus,
    clock: FrozenClock,
    ids: SequentialIdFactory,
    providers: Any,
) -> Any:
    from app.repositories.consent import AuditRepository, IngestRawRepository
    from app.repositories.intakes import IntakeRepository
    from app.services.ingest import IngestService

    return IngestService(
        intakes=IntakeRepository(session),
        raw=IngestRawRepository(session),
        audit=AuditRepository(session),
        bus=bus,
        clock=clock,
        ids=ids,
        repair_provider=providers.repair,
    )


@pytest.fixture
def document_service(
    session: AsyncSession,
    bus: InProcessBus,
    clock: FrozenClock,
    ids: SequentialIdFactory,
    providers: Any,
    content: ClinicalContent,
    settings: Settings,
) -> Any:
    from app.repositories.documents import DocumentRepository
    from app.repositories.intakes import IntakeRepository
    from app.services.documents import DocumentService

    return DocumentService(
        documents=DocumentRepository(session),
        intakes=IntakeRepository(session),
        storage=providers.storage,
        ocr=providers.ocr,
        bus=bus,
        clock=clock,
        ids=ids,
        interactions=content.interactions,
        ingredients=content.ingredients,
        confidence_floor=settings.ocr_confidence_floor,
    )


@pytest.fixture
def report_service(
    session: AsyncSession,
    bus: InProcessBus,
    still_clock: FrozenClock,
    ids: SequentialIdFactory,
    providers: Any,
    content: ClinicalContent,
) -> Any:
    from app.domain.report.builder import FieldLabels
    from app.repositories.consent import AuditRepository, ReportRepository
    from app.repositories.documents import DocumentRepository
    from app.repositories.intakes import IntakeRepository
    from app.repositories.patients import PatientLinkRepository
    from app.services.reports import ReportService
    from app.services.timeline import TimelineService

    return ReportService(
        intakes=IntakeRepository(session),
        documents=DocumentRepository(session),
        reports=ReportRepository(session),
        audit=AuditRepository(session),
        templates=content.templates,
        labels=FieldLabels(content.field_labels()),
        interactions=content.interactions,
        ingredients=content.ingredients,
        bus=bus,
        clock=still_clock,
        ids=ids,
        links=PatientLinkRepository(session),
        timeline=TimelineService(
            provider=providers.timeline, clock=still_clock
        ),
    )


@pytest.fixture
def worklist_service(
    session: AsyncSession, bus: InProcessBus, clock: FrozenClock, content: ClinicalContent
) -> Any:
    from app.repositories.consent import AuditRepository
    from app.repositories.intakes import IntakeRepository
    from app.services.worklist import WorklistService

    return WorklistService(
        intakes=IntakeRepository(session),
        audit=AuditRepository(session),
        bus=bus,
        clock=clock,
        session=session,
        ingredients=content.ingredients,
    )


@pytest.fixture
def identity_service(
    session: AsyncSession,
    clock: FrozenClock,
    ids: SequentialIdFactory,
    providers: Any,
    content: ClinicalContent,
) -> Any:
    from app.repositories.intakes import IntakeRepository
    from app.repositories.patients import PatientLinkRepository, PatientRepository
    from app.services.identity import IdentityService

    return IdentityService(
        patients=PatientRepository(session),
        intakes=IntakeRepository(session),
        abha=providers.abha,
        clock=clock,
        ids=ids,
        links=PatientLinkRepository(session),
        labels=content.field_labels(),
    )


# --- HTTP client -------------------------------------------------------------


@pytest.fixture
def app_client(engine: Any, settings: Settings, still_clock: FrozenClock) -> Iterator[Any]:
    """A `TestClient` wired to the in-memory database.

    Overrides settings, the clock and the id factory so API tests are as
    deterministic as the unit tests.
    """
    from fastapi.testclient import TestClient

    from app import db as db_module
    from app.api import auth, deps
    from app.core import config as config_module
    from app.core.content import get_clinical_content
    from app.events.bus import reset_event_bus
    from app.main import create_app

    config_module.get_settings.cache_clear()
    get_clinical_content.cache_clear()
    reset_event_bus()
    deps.reset_providers()

    db_module.configure(engine)
    original = config_module.get_settings
    config_module.get_settings = lambda: settings  # type: ignore[assignment]

    application = create_app()
    application.dependency_overrides[deps.get_settings_dep] = lambda: settings
    application.dependency_overrides[auth.auth_settings] = lambda: settings
    application.dependency_overrides[deps.get_clock] = lambda: still_clock
    # One factory for the whole client, not one per request. Rebuilding it per
    # request restarts the counter, so two calls that each mint a fact id both
    # mint `fact_000001` — which collides on insert the moment a test performs
    # two writes. Deterministic must still mean unique.
    sequential_ids = SequentialIdFactory()
    application.dependency_overrides[deps.get_ids] = lambda: sequential_ids

    with TestClient(application) as client:
        yield client

    config_module.get_settings = original  # type: ignore[assignment]
    config_module.get_settings.cache_clear()
    get_clinical_content.cache_clear()
    reset_event_bus()
    deps.reset_providers()


#: Headers for each role, for API tests.
KIOSK_HEADERS = {"Authorization": "Bearer test-kiosk-token"}
STAFF_HEADERS = {
    "X-User-Id": "staff-1",
    "X-User-Role": "staff",
    "X-Hospital-Id": HOSPITAL_ID,
}
PHYSICIAN_HEADERS = {
    "X-User-Id": "dr-sharma",
    "X-User-Role": "physician",
    "X-Hospital-Id": HOSPITAL_ID,
}
ADMIN_HEADERS = {
    "X-User-Id": "admin-1",
    "X-User-Role": "admin",
    "X-Hospital-Id": HOSPITAL_ID,
}
OTHER_STAFF_HEADERS = {
    "X-User-Id": "staff-2",
    "X-User-Role": "staff",
    "X-Hospital-Id": OTHER_HOSPITAL_ID,
}
