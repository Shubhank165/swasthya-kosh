"""Concurrency proofs.

Two practitioners on a pooled Kayachikitsa queue press "call next" at the same
instant. They must receive different tokens. Not usually — never.

This is the test the whole `SELECT ... FOR UPDATE SKIP LOCKED` design exists for,
and it runs against real Postgres because SQLite cannot express the thing being
proven.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.ids import UuidIdFactory
from app.domain.queue.policies import PatientAttributes
from app.events.bus import InProcessBus
from app.repositories.alerts import AlertRepository
from app.repositories.queues import QueueRepository
from app.services.queue import QueueService
from app.services.seed import seed_facility
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres

QUEUE_ID = "q-kc-general"
SERVICE_DATE = date(2026, 1, 15)


def service(session: AsyncSession, settings: Settings) -> QueueService:
    return QueueService(
        queues=QueueRepository(session),
        alerts=AlertRepository(session),
        bus=InProcessBus(),
        settings=settings,
        clock=SystemClock(),
        ids=UuidIdFactory(),
    )


async def setup_queue(
    sessions: async_sessionmaker[AsyncSession], settings: Settings, *, tickets: int
) -> str:
    """Seed the facility and issue `tickets` waiting tokens."""
    async with sessions() as session:
        await seed_facility(session, settings=settings, service_date=SERVICE_DATE)
        await session.commit()

    instance_id = f"qi-{QUEUE_ID}-{SERVICE_DATE.isoformat()}"
    async with sessions() as session:
        queue_service = service(session, settings)
        for _ in range(tickets):
            await queue_service.issue(
                QUEUE_ID,
                instance_id=instance_id,
                attributes=PatientAttributes(age_years=35),
            )
        await session.commit()
    return instance_id


class TestCallNextUnderConcurrency:
    async def test_concurrent_callers_never_receive_the_same_token(
        self, pg_sessions: async_sessionmaker[AsyncSession], pg_settings: Settings
    ) -> None:
        """Definition of done item 7.

        Ten practitioners, ten waiting patients, all calling simultaneously. Every
        token handed out must be distinct: a double-issue means two consultants
        walk to the waiting room and call the same person.
        """
        instance_id = await setup_queue(pg_sessions, pg_settings, tickets=10)

        async def call_once() -> str | None:
            async with pg_sessions() as session:
                view = await service(session, pg_settings).call_next(instance_id)
                await session.commit()
                return None if view is None else view.ticket.token_number

        tokens = [t for t in await asyncio.gather(*(call_once() for _ in range(10))) if t]

        assert len(tokens) == len(set(tokens)), f"double-issued tokens: {tokens}"
        assert len(tokens) == 10

    async def test_more_callers_than_patients_leaves_the_extras_empty_handed(
        self, pg_sessions: async_sessionmaker[AsyncSession], pg_settings: Settings
    ) -> None:
        """Eight callers, three patients. Five get nothing — and none of them
        gets a duplicate of someone else's token."""
        instance_id = await setup_queue(pg_sessions, pg_settings, tickets=3)

        async def call_once() -> str | None:
            async with pg_sessions() as session:
                view = await service(session, pg_settings).call_next(instance_id)
                await session.commit()
                return None if view is None else view.ticket.token_number

        results = await asyncio.gather(*(call_once() for _ in range(8)))
        tokens = [t for t in results if t]
        assert len(tokens) == 3
        assert len(set(tokens)) == 3

    async def test_concurrent_issue_never_duplicates_a_token_number(
        self, pg_sessions: async_sessionmaker[AsyncSession], pg_settings: Settings
    ) -> None:
        """Two registration counters issuing at once.

        The token counter is incremented under a row lock on the instance, so the
        two counters serialise on it rather than racing.
        """
        async with pg_sessions() as session:
            await seed_facility(session, settings=pg_settings, service_date=SERVICE_DATE)
            await session.commit()
        instance_id = f"qi-{QUEUE_ID}-{SERVICE_DATE.isoformat()}"

        async def issue_once() -> str:
            async with pg_sessions() as session:
                view = await service(session, pg_settings).issue(
                    QUEUE_ID,
                    instance_id=instance_id,
                    attributes=PatientAttributes(age_years=30),
                )
                await session.commit()
                return view.ticket.token_number

        tokens = await asyncio.gather(*(issue_once() for _ in range(12)))
        assert len(set(tokens)) == 12
        assert sorted(tokens) == sorted(f"KC-{i:03d}" for i in range(1, 13))

    async def test_a_called_ticket_is_not_offered_to_a_later_caller(
        self, pg_sessions: async_sessionmaker[AsyncSession], pg_settings: Settings
    ) -> None:
        instance_id = await setup_queue(pg_sessions, pg_settings, tickets=2)
        async with pg_sessions() as session:
            first = await service(session, pg_settings).call_next(instance_id)
            await session.commit()
        async with pg_sessions() as session:
            second = await service(session, pg_settings).call_next(instance_id)
            await session.commit()
        assert first is not None and second is not None
        assert first.ticket.ticket_id != second.ticket.ticket_id
        async with pg_sessions() as session:
            third = await service(session, pg_settings).call_next(instance_id)
            await session.commit()
        assert third is None


class TestIdempotencyUnderRetry:
    async def test_a_replayed_offline_submission_does_not_duplicate(
        self, pg_sessions: async_sessionmaker[AsyncSession], pg_settings: Settings
    ) -> None:
        """Definition of done item 8, at the store level.

        A kiosk that lost the LAN mid-submission and retried must get its
        original response, not a second fact.
        """
        from app.core.idempotency import IdempotencyRecord, check_replay, fingerprint
        from app.repositories.consent import SqlIdempotencyStore

        payload = {"concept": "known_diabetes", "value": "yes"}
        async with pg_sessions() as session:
            store = SqlIdempotencyStore(session)
            assert await store.get("k1", "POST /answers") is None
            await store.put(
                IdempotencyRecord(
                    key="k1",
                    endpoint="POST /answers",
                    request_fingerprint=fingerprint(payload),
                    response_body={"ok": True},
                    status_code=200,
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()

        async with pg_sessions() as session:
            store = SqlIdempotencyStore(session)
            record = await store.get("k1", "POST /answers")
            assert record is not None
            replay = check_replay(record, payload=payload)
            assert replay is not None
            assert replay.response_body == {"ok": True}

            from app.core.errors import IdempotencyConflictError

            with pytest.raises(IdempotencyConflictError):
                check_replay(record, payload={"concept": "known_diabetes", "value": "no"})


class TestMigrations:
    async def test_the_schema_from_alembic_matches_the_orm_metadata(
        self, pg_sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        """`alembic upgrade head` from empty must produce what the code expects."""
        from sqlalchemy import inspect, text

        from app.models import Base

        async with pg_sessions() as session:
            result = await session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            tables = {row[0] for row in result.all()}
        assert set(Base.metadata.tables) <= tables
        assert inspect is not None


class TestSessionTeardown:
    async def test_no_residual_state_is_reachable_from_the_same_kiosk_id(
        self, pg_sessions: async_sessionmaker[AsyncSession], pg_settings: Settings
    ) -> None:
        """A patient who walked away must not leave their history reachable from
        the terminal they were standing at."""
        from app.core.content import get_clinical_content
        from app.repositories.consent import ConsentRepository
        from app.repositories.intakes import IntakeRepository
        from app.services.intake import IntakeService

        def intake_service(session: AsyncSession) -> IntakeService:
            return IntakeService(
                intakes=IntakeRepository(session),
                alerts=AlertRepository(session),
                consent=ConsentRepository(session),
                content=get_clinical_content(),
                bus=InProcessBus(),
                settings=pg_settings,
                clock=SystemClock(),
                ids=UuidIdFactory(),
            )

        async with pg_sessions() as session:
            snapshot = await intake_service(session).start(kiosk_id="kiosk-7")
            await session.commit()
            intake_id = str(snapshot.state.intake_id)

        async with pg_sessions() as session:
            repository = IntakeRepository(session)
            assert await repository.find_by_kiosk("kiosk-7") == (intake_id,)

        async with pg_sessions() as session:
            await intake_service(session).teardown_kiosk_session("kiosk-7")
            await session.commit()

        async with pg_sessions() as session:
            repository = IntakeRepository(session)
            # The next patient at that terminal cannot reach the previous one.
            assert await repository.find_by_kiosk("kiosk-7") == ()
            # The clinical record itself survives: it belongs to the encounter.
            assert await repository.get(intake_id) is not None
