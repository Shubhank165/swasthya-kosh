"""The seeded slots, shelf and orders — and what they have to show.

A demo is credible when the distinctions the code makes are visible in it. This
module is the guard on that: it asserts the seed puts all three order outcomes
and every actionable stock state on one screen, so a change that quietly
collapses `unfilled` into `requested`, or drops the expired box, fails here
rather than in front of a reviewer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import SystemClock
from app.core.ids import SequentialIdFactory
from app.db.tenancy import tenant_scope
from app.domain.coordination import ACTIONABLE_STOCK, OrderStatus, StockState
from app.services.coordination import CoordinationService
from app.services.seed import seed
from tests.conftest import HOSPITAL_ID


@pytest.fixture
async def session(engine: Any) -> AsyncIterator[AsyncSession]:
    """A session with no hospital yet — `seed()` short-circuits on one."""
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as opened:
        with tenant_scope(HOSPITAL_ID):
            yield opened
        await opened.rollback()


def _service(session: AsyncSession) -> CoordinationService:
    return CoordinationService(
        session=session,
        clock=SystemClock(),
        ids=SequentialIdFactory(start=9000),
        hospital_id=HOSPITAL_ID,
    )


class TestTheSeededOrders:
    async def test_all_three_outcomes_are_on_the_screen(self, session: Any) -> None:
        """Scheduled, unfilled and requested. The middle one is the point.

        A referral that found no capacity reads `unfilled`, which is a different
        answer from `requested` — and a demo where every order happens to find a
        slot never shows that the difference exists.
        """

        result = await seed(session)
        intake_id = result["intakes"][0]
        orders = await _service(session).orders_for(intake_id)
        statuses = {order.status for order in orders}

        assert OrderStatus.SCHEDULED.value in statuses
        assert OrderStatus.UNFILLED.value in statuses
        assert OrderStatus.REQUESTED.value in statuses

    async def test_the_scan_carries_a_time_and_the_referral_does_not(
        self, session: Any
    ) -> None:
        result = await seed(session)
        orders = await _service(session).orders_for(result["intakes"][0])
        by_destination = {order.destination: order for order in orders}

        assert by_destination["radiology"].slot_at is not None
        # Not a nearest-miss with a blank time: nothing was offered, and the
        # record says so rather than sending a patient across a site to find out.
        assert by_destination["physiotherapy"].slot_at is None
        assert by_destination["physiotherapy"].slot_id is None


class TestTheSeededShelf:
    async def test_every_state_a_pharmacist_acts_on_is_represented(
        self, session: Any
    ) -> None:
        await seed(session)
        alerts = await _service(session).stock_alerts()
        assert {state for _, state in alerts} == ACTIONABLE_STOCK

    async def test_a_well_stocked_item_is_not_an_alert(self, session: Any) -> None:
        """The shelf holds more than the alerts show. A pharmacy view listing
        everything it holds is an inventory report, not a warning."""

        await seed(session)
        service = _service(session)
        alerted = {item.code for item, _ in await service.stock_alerts()}
        assert "cetirizine_10" not in alerted
        states = await service.stock_for(["cetirizine_10"])
        assert states["cetirizine_10"] is StockState.AVAILABLE

    async def test_a_medicine_nobody_recorded_reads_unknown_not_out(
        self, session: Any
    ) -> None:
        """The seed cannot contain a row for this, by definition — which is
        exactly what makes it worth asserting here."""

        await seed(session)
        states = await _service(session).stock_for(["not_a_stocked_medicine"])
        assert states["not_a_stocked_medicine"] is StockState.UNKNOWN


class TestRunningItTwice:
    async def test_a_second_seed_adds_no_orders(self, session: Any) -> None:
        """A rehearsed demo has to read the same on the second run."""

        result = await seed(session)
        intake_id = result["intakes"][0]
        before = len(await _service(session).orders_for(intake_id))
        again = await seed(session)
        assert again["created"] is False
        assert len(await _service(session).orders_for(intake_id)) == before
