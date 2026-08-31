"""Shared fixtures.

Everything here is deterministic: a frozen clock, sequential ids, an in-memory
bus. A test that passes today must pass identically in six months, because the
whole point of the deterministic core is that its behaviour is reproducible.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.content import ClinicalContent, load_clinical_content
from app.core.ids import SequentialIdFactory
from app.domain.clinical.enums import (
    Certainty,
    FactStatus,
    ReporterRole,
    Section,
    SourceType,
    Temporality,
)
from app.domain.clinical.fact import ClinicalFact
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.clinical.provenance import (
    ConceptRef,
    FactId,
    IntakeId,
    SegmentId,
    SourceRef,
)
from app.domain.statemachine.engine import ClinicalStateMachine
from app.events.bus import InProcessBus, reset_event_bus
from app.models import Base

START = datetime(2026, 1, 15, 9, 0, 0, tzinfo=UTC)


@pytest.fixture
def settings() -> Settings:
    """Settings pinned to the repo's own clinical content."""
    return Settings(environment="test", database_url="sqlite+aiosqlite:///:memory:")


@pytest.fixture(scope="session")
def content() -> ClinicalContent:
    """Loaded once: parsing every pathway per test would dominate the suite."""
    return load_clinical_content(Settings(environment="test"))


@pytest.fixture
def clock() -> FrozenClock:
    """Advances one second per read, so recorded_at ordering is meaningful."""
    return FrozenClock(start=START, step=timedelta(seconds=1))


@pytest.fixture
def ids() -> SequentialIdFactory:
    return SequentialIdFactory()


@pytest.fixture
def machine(content: ClinicalContent) -> ClinicalStateMachine:
    return ClinicalStateMachine(content.content_set)


@pytest.fixture
def empty_state() -> PatientIntakeState:
    return PatientIntakeState(intake_id=IntakeId("intake_test"))


@pytest.fixture
def bus() -> InProcessBus:
    reset_event_bus()
    instance = InProcessBus()
    instance.record_history(True)
    return instance


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A real database on SQLite, schema built from the ORM metadata.

    SQLite for speed; the concurrency proof that needs `FOR UPDATE SKIP LOCKED`
    runs against Postgres in `tests/integration/`.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as db:
        yield db
    await engine.dispose()


# --- fact construction helpers -----------------------------------------------


def make_fact(
    concept: str,
    *,
    status: FactStatus = FactStatus.PRESENT,
    value: object | None = None,
    fact_id: str | None = None,
    section: Section = Section.HPI,
    source_type: SourceType = SourceType.VOICE,
    certainty: Certainty = Certainty.REPORTED,
    temporality: Temporality = Temporality.CURRENT,
    confidence: float = 0.9,
    reported_by: ReporterRole = ReporterRole.SELF,
    original_expression: str | None = None,
    original_language: str | None = None,
    recorded_at: datetime | None = None,
    supersedes: str | None = None,
    patient_confirmed: bool = False,
    physician_verified: bool = False,
    display: str | None = None,
) -> ClinicalFact:
    """Build a fact with sensible defaults. Used across the whole suite."""
    if source_type is SourceType.DOCUMENT:
        from app.domain.clinical.provenance import DocumentId

        ref = SourceRef.from_document(DocumentId("Discharge_summary_2.jpg"), page=1)
    elif source_type in {SourceType.VOICE}:
        ref = SourceRef.from_transcript(SegmentId("seg-1"), 0, 1200)
    else:
        ref = SourceRef.from_actor(source_type.value)
    return ClinicalFact(
        fact_id=FactId(fact_id or f"fact_{concept}"),
        concept=ConceptRef(concept, display=display),
        status=status,
        certainty=certainty,
        temporality=temporality,
        source_type=source_type,
        source_ref=ref,
        confidence=confidence,
        reported_by=reported_by,
        recorded_at=recorded_at or START,
        section=section,
        value=value,  # type: ignore[arg-type]
        original_expression=original_expression,
        original_language=original_language,
        patient_confirmed=patient_confirmed,
        physician_verified=physician_verified,
        supersedes=FactId(supersedes) if supersedes else None,
    )


@pytest.fixture
def fact_factory():  # type: ignore[no-untyped-def]
    return make_fact
