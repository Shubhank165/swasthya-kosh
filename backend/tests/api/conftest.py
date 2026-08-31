"""API test fixtures: a real app against a real (SQLite) database."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_clock, get_ids, get_settings_dep
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.ids import SequentialIdFactory
from app.db import get_session
from app.events.bus import InProcessBus, get_event_bus
from app.main import create_app
from app.models import Base
from app.services.seed import seed_facility
from tests.conftest import START

#: Headers for each role. Real authentication is the hospital's identity
#: provider; these exercise the same role checks the endpoints enforce.
STAFF = {"X-User-Id": "staff-1", "X-User-Role": "staff"}
TRIAGE = {"X-User-Id": "triage-1", "X-User-Role": "triage"}
PHYSICIAN = {"X-User-Id": "dr-1", "X-User-Role": "physician"}
KIOSK = {"X-User-Id": "kiosk-1", "X-User-Role": "patient_session"}


@pytest_asyncio.fixture
async def api() -> AsyncIterator[AsyncClient]:
    """An app wired to an in-memory database, a frozen clock and sequential ids.

    Deterministic end to end: the same request sequence produces the same ids
    and the same timestamps every run.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    settings = Settings(environment="test", database_url="sqlite+aiosqlite:///:memory:")
    clock = FrozenClock(start=START)
    ids = SequentialIdFactory()
    bus = InProcessBus()
    bus.record_history(True)

    async with factory() as seed_session:
        await seed_facility(seed_session, settings=settings, clock=clock)
        await seed_session.commit()

    async def _session() -> AsyncIterator[AsyncSession]:
        async with factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_ids] = lambda: ids
    app.dependency_overrides[get_event_bus] = lambda: bus

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.bus = bus  # type: ignore[attr-defined]
        client.clock = clock  # type: ignore[attr-defined]
        yield client
    await engine.dispose()
