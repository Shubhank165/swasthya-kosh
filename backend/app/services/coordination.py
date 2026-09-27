"""Issuing orders, filling slots, reading the shelf, counting the queue.

This layer does I/O. Every decision it acts on comes from
`app.domain.coordination`, which is pure — the same split the report builder
uses, so the decisions stay testable without a database and this file stays
reviewable as plumbing.

**Tenancy.** Every query filters on `hospital_id`, which the tenancy guard
enforces rather than trusts: an unscoped SELECT against these tables raises.
The hospital comes from the caller's principal and never from a request body.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.core.ids import IdFactory
from app.core.logging import get_logger
from app.domain.coordination import (
    ACTIONABLE_STOCK,
    DepartmentLoad,
    OrderKind,
    OrderStatus,
    QueueEstimate,
    Slot,
    StockItem,
    StockState,
    department_loads,
    estimate_wait,
    next_free_slot,
    stock_state,
)
from app.models.clinical import (
    CareOrderRecord,
    IntakeRecord,
    PharmacyStockRecord,
    RedFlagEventRecord,
    ServiceSlotRecord,
)

logger = get_logger(__name__)

#: How far ahead a referral looks for capacity. Beyond a fortnight the answer
#: is "book it properly", not "here is a slot".
SLOT_HORIZON = timedelta(days=14)

#: The window the operations view counts over.
LOAD_WINDOW = timedelta(hours=24)


class CoordinationService:
    """What happens to a patient after the consultation."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        clock: Clock,
        ids: IdFactory,
        hospital_id: str,
    ) -> None:
        self._session = session
        self._clock = clock
        self._ids = ids
        self._hospital_id = hospital_id

    # ------------------------------------------------------------------ orders

    async def issue(
        self,
        *,
        intake_id: str,
        kind: OrderKind,
        code: str,
        display: str,
        ordered_by: str,
        destination: str | None = None,
        note: str | None = None,
    ) -> CareOrderRecord:
        """Record one order, and give it a slot if the destination has one.

        A referral or a scan that finds no free slot is stored `UNFILLED`, not
        `REQUESTED` with a blank time. The distinction is the point: one says
        the hospital could not offer an appointment, the other says nobody has
        looked yet, and a patient sent across a site deserves to know which.
        """

        now = self._clock.now()
        #: Kinds that go somewhere with a diary. A prescription does not: the
        #: pharmacy counter has no appointment to offer.
        bookable = {OrderKind.REFERRAL, OrderKind.IMAGING, OrderKind.LAB}

        slot: Slot | None = None
        status = OrderStatus.REQUESTED
        if destination is not None and kind in bookable:
            slot = await self._claim_slot(destination=destination, after=now)
            status = OrderStatus.SCHEDULED if slot is not None else OrderStatus.UNFILLED

        record = CareOrderRecord(
            id=self._ids.new_id("ord"),
            hospital_id=self._hospital_id,
            intake_id=intake_id,
            kind=kind.value,
            code=code,
            display=display,
            status=status.value,
            destination=destination,
            slot_id=slot.slot_id if slot else None,
            slot_at=slot.starts_at if slot else None,
            ordered_by=ordered_by,
            note=note,
            created_at=now,
            updated_at=now,
        )
        self._session.add(record)
        await self._session.flush()
        logger.info(
            "care_order_issued",
            extra={
                "order_id": record.id,
                "kind": kind.value,
                "status": status.value,
                "scheduled": slot is not None,
            },
        )
        return record

    async def orders_for(self, intake_id: str) -> tuple[CareOrderRecord, ...]:
        result = await self._session.execute(
            select(CareOrderRecord)
            .where(
                CareOrderRecord.hospital_id == self._hospital_id,
                CareOrderRecord.intake_id == intake_id,
            )
            .order_by(CareOrderRecord.created_at, CareOrderRecord.id)
        )
        return tuple(result.scalars())

    async def _claim_slot(self, *, destination: str, after: datetime) -> Slot | None:
        """Take the earliest free slot at a destination, or nothing.

        The increment and the read happen in one transaction, so two doctors
        referring at the same moment cannot both take the last place.
        """

        result = await self._session.execute(
            select(ServiceSlotRecord).where(
                ServiceSlotRecord.hospital_id == self._hospital_id,
                ServiceSlotRecord.destination == destination,
                ServiceSlotRecord.starts_at >= after,
                ServiceSlotRecord.starts_at <= after + SLOT_HORIZON,
            )
        )
        rows = {row.id: row for row in result.scalars()}
        chosen = next_free_slot(
            [
                Slot(
                    slot_id=row.id,
                    destination=row.destination,
                    starts_at=row.starts_at,
                    capacity=row.capacity,
                    booked=row.booked,
                )
                for row in rows.values()
            ],
            after=after,
        )
        if chosen is None:
            return None
        rows[chosen.slot_id].booked += 1
        await self._session.flush()
        return chosen

    # ------------------------------------------------------------------ pharmacy

    async def stock_for(
        self, codes: Sequence[str], *, today: date | None = None
    ) -> dict[str, StockState]:
        """How the shelf reads for each code asked about.

        A code the pharmacy has never told us about comes back `UNKNOWN`, not
        missing from the mapping — the caller asked a question and is owed an
        answer to it.
        """

        today = today or self._clock.now().date()
        if not codes:
            return {}
        result = await self._session.execute(
            select(PharmacyStockRecord).where(
                PharmacyStockRecord.hospital_id == self._hospital_id,
                PharmacyStockRecord.code.in_(list(codes)),
            )
        )
        held = {
            row.code: StockItem(
                code=row.code,
                display=row.display,
                on_hand=row.on_hand,
                reorder_level=row.reorder_level,
                expires_on=row.expires_on,
            )
            for row in result.scalars()
        }
        return {code: stock_state(held.get(code), today=today) for code in codes}

    async def stock_alerts(
        self, *, today: date | None = None
    ) -> tuple[tuple[StockItem, StockState], ...]:
        """Everything a pharmacist should see before a patient reaches the counter."""

        today = today or self._clock.now().date()
        result = await self._session.execute(
            select(PharmacyStockRecord)
            .where(PharmacyStockRecord.hospital_id == self._hospital_id)
            .order_by(PharmacyStockRecord.code)
        )
        alerts = []
        for row in result.scalars():
            item = StockItem(
                code=row.code,
                display=row.display,
                on_hand=row.on_hand,
                reorder_level=row.reorder_level,
                expires_on=row.expires_on,
            )
            state = stock_state(item, today=today)
            if state in ACTIONABLE_STOCK:
                alerts.append((item, state))
        return tuple(alerts)

    # ------------------------------------------------------------------ waiting

    async def wait_estimate(
        self, *, intake_id: str, department_code: str | None
    ) -> QueueEstimate:
        """Where this patient stands, and how long that is likely to be.

        The rate is what this department actually did today. A department that
        has not seen enough patients yet gets a position and no time, and says
        so rather than guessing.
        """

        now = self._clock.now()
        since = now - LOAD_WINDOW
        waiting = await self._session.execute(
            select(IntakeRecord.id, IntakeRecord.received_at)
            .where(
                IntakeRecord.hospital_id == self._hospital_id,
                IntakeRecord.received_at >= since,
                IntakeRecord.seen_at.is_(None),
                *( [IntakeRecord.department_code == department_code] if department_code else [] ),
            )
            .order_by(IntakeRecord.received_at, IntakeRecord.id)
        )
        ordered = [row.id for row in waiting]
        position = ordered.index(intake_id) + 1 if intake_id in ordered else len(ordered) + 1

        seen = await self._session.execute(
            select(IntakeRecord.received_at, IntakeRecord.seen_at).where(
                IntakeRecord.hospital_id == self._hospital_id,
                IntakeRecord.seen_at.is_not(None),
                IntakeRecord.received_at >= since,
                *( [IntakeRecord.department_code == department_code] if department_code else [] ),
            )
        )
        minutes = [
            (row.seen_at - row.received_at).total_seconds() / 60
            for row in seen
            if row.seen_at is not None and row.seen_at > row.received_at
        ]
        return estimate_wait(position=position, completed_minutes=minutes)

    # ------------------------------------------------------------------ operations

    async def load(self) -> tuple[DepartmentLoad, ...]:
        """Where the time is going, counted over the last day."""

        now = self._clock.now()
        since = now - LOAD_WINDOW
        waiting = await self._session.execute(
            select(IntakeRecord.id, IntakeRecord.department_code, IntakeRecord.received_at).where(
                IntakeRecord.hospital_id == self._hospital_id,
                IntakeRecord.received_at >= since,
                IntakeRecord.seen_at.is_(None),
            )
        )
        rows = list(waiting)
        flagged_result = await self._session.execute(
            select(RedFlagEventRecord.intake_id).where(
                RedFlagEventRecord.hospital_id == self._hospital_id,
                RedFlagEventRecord.acknowledged_by.is_(None),
            )
        )
        flagged = set(flagged_result.scalars())

        unfilled_result = await self._session.execute(
            select(CareOrderRecord.destination, func.count())
            .where(
                CareOrderRecord.hospital_id == self._hospital_id,
                CareOrderRecord.status == OrderStatus.UNFILLED.value,
            )
            .group_by(CareOrderRecord.destination)
        )
        unfilled = {
            destination: count
            for destination, count in unfilled_result
            if destination is not None
        }

        return department_loads(
            rows=[(row.department_code, row.received_at, row.id in flagged) for row in rows],
            unfilled=unfilled,
            now=now,
        )

    async def require_intake(self, intake_id: str) -> IntakeRecord:
        result = await self._session.execute(
            select(IntakeRecord).where(
                IntakeRecord.hospital_id == self._hospital_id,
                IntakeRecord.id == intake_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError(f"intake {intake_id} not found")
        return row
