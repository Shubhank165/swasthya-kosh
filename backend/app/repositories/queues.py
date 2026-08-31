"""Queue repository.

Two operations here have to be right under concurrency, and they are the reason
this module exists rather than the domain talking to the session directly.

`next_sequence` takes a row lock on the instance before incrementing the token
counter, so two counters issuing simultaneously cannot hand out the same number.

`call_next` selects candidate tickets `FOR UPDATE SKIP LOCKED`. Two practitioners
on a pooled Kayachikitsa queue pressing "call next" at the same instant each get
a different token — the second skips the row the first has locked rather than
blocking on it or, worse, reading it.

SQLite ignores `FOR UPDATE`, so the integration suite runs the concurrency proof
against Postgres and the fast unit suite runs the ordering logic in memory.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.domain.clinical.enums import IntakeState
from app.domain.clinical.provenance import IntakeId
from app.domain.queue.entities import (
    CLOSED_STATES,
    Department,
    Queue,
    QueueInstance,
    QueueState,
    Ticket,
)
from app.domain.queue.ordering import IntakeStateLookup
from app.models.clinical import IntakeRecord
from app.models.queue import (
    DepartmentRecord,
    QueueInstanceRecord,
    QueueRecord,
    TicketRecord,
)
from app.repositories.mappers import (
    apply_instance_to_row,
    apply_ticket_to_row,
    department_from_row,
    instance_from_row,
    queue_from_row,
    ticket_from_row,
    ticket_to_row,
)

#: States a ticket may be called from. Used by both the candidate read and the
#: re-check inside the row lock, so the two can never disagree.
_CALLABLE_STATE_VALUES: tuple[str, ...] = (
    QueueState.ISSUED.value,
    QueueState.WAITING.value,
    QueueState.DEFERRED.value,
    QueueState.ESCALATED.value,
)


class QueueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    def _supports_row_locking(self) -> bool:
        """SQLite has no `FOR UPDATE`; asking for it there is an error, not a no-op."""
        return self._session.bind is not None and self._session.bind.dialect.name != "sqlite"

    # --- departments and queues ---------------------------------------------

    async def list_departments(self) -> tuple[Department, ...]:
        result = await self._session.execute(
            select(DepartmentRecord).order_by(DepartmentRecord.code)
        )
        return tuple(department_from_row(r) for r in result.scalars().all())

    async def get_queue(self, queue_id: str) -> Queue | None:
        row = await self._session.get(QueueRecord, queue_id)
        return None if row is None else queue_from_row(row)

    async def require_queue(self, queue_id: str) -> Queue:
        queue = await self.get_queue(queue_id)
        if queue is None:
            raise NotFoundError(f"queue {queue_id} not found", details={"queue_id": queue_id})
        return queue

    async def list_queues(self, *, department_code: str | None = None) -> tuple[Queue, ...]:
        stmt = select(QueueRecord).order_by(QueueRecord.id)
        if department_code:
            stmt = stmt.where(QueueRecord.department_code == department_code)
        result = await self._session.execute(stmt)
        return tuple(queue_from_row(r) for r in result.scalars().all())

    # --- instances ------------------------------------------------------------

    async def get_instance(self, instance_id: str) -> QueueInstance | None:
        row = await self._session.get(QueueInstanceRecord, instance_id)
        return None if row is None else instance_from_row(row)

    async def require_instance(self, instance_id: str) -> QueueInstance:
        instance = await self.get_instance(instance_id)
        if instance is None:
            raise NotFoundError(
                f"queue instance {instance_id} not found", details={"instance_id": instance_id}
            )
        return instance

    async def instance_for(
        self, queue_id: str, *, service_date: date, session_name: str
    ) -> QueueInstance | None:
        result = await self._session.execute(
            select(QueueInstanceRecord).where(
                QueueInstanceRecord.queue_id == queue_id,
                QueueInstanceRecord.service_date == service_date,
                QueueInstanceRecord.session == session_name,
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else instance_from_row(row)

    async def list_instances(
        self, *, service_date: date, department_code: str | None = None
    ) -> tuple[QueueInstance, ...]:
        stmt = (
            select(QueueInstanceRecord)
            .join(QueueRecord, QueueRecord.id == QueueInstanceRecord.queue_id)
            .where(QueueInstanceRecord.service_date == service_date)
            .order_by(QueueInstanceRecord.id)
        )
        if department_code:
            stmt = stmt.where(QueueRecord.department_code == department_code)
        result = await self._session.execute(stmt)
        return tuple(instance_from_row(r) for r in result.scalars().all())

    async def create_instance(self, instance: QueueInstance) -> QueueInstance:
        row = QueueInstanceRecord(
            id=str(instance.instance_id),
            queue_id=str(instance.queue_id),
            service_date=instance.service_date,
            session=instance.session.value,
        )
        apply_instance_to_row(row, instance)
        self._session.add(row)
        await self._session.flush()
        return instance_from_row(row)

    async def save_instance(self, instance: QueueInstance) -> None:
        row = await self._session.get(QueueInstanceRecord, str(instance.instance_id))
        if row is None:
            raise NotFoundError(f"queue instance {instance.instance_id} not found")
        apply_instance_to_row(row, instance)
        await self._session.flush()

    async def next_sequence(self, instance_id: str) -> int:
        """Reserve the next token number under a row lock.

        The lock is on the instance row, so concurrent `issue` calls serialise on
        the counter rather than racing it. This is the narrowest lock that makes
        token numbers unique, and it is held for the length of one increment.
        """
        stmt = select(QueueInstanceRecord).where(QueueInstanceRecord.id == instance_id)
        if self._supports_row_locking():
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError(f"queue instance {instance_id} not found")
        row.last_issued += 1
        await self._session.flush()
        return row.last_issued

    # --- tickets --------------------------------------------------------------

    async def get_ticket(self, ticket_id: str) -> Ticket | None:
        row = await self._session.get(TicketRecord, ticket_id)
        return None if row is None else ticket_from_row(row)

    async def require_ticket(self, ticket_id: str) -> Ticket:
        ticket = await self.get_ticket(ticket_id)
        if ticket is None:
            raise NotFoundError(f"ticket {ticket_id} not found", details={"ticket_id": ticket_id})
        return ticket

    async def add_ticket(self, ticket: Ticket) -> None:
        self._session.add(ticket_to_row(ticket))
        await self._session.flush()

    async def save_ticket(self, ticket: Ticket) -> None:
        row = await self._session.get(TicketRecord, str(ticket.ticket_id))
        if row is None:
            raise NotFoundError(f"ticket {ticket.ticket_id} not found")
        apply_ticket_to_row(row, ticket)
        await self._session.flush()

    async def save_tickets(self, tickets: tuple[Ticket, ...]) -> None:
        for ticket in tickets:
            await self.save_ticket(ticket)

    async def list_tickets(
        self, instance_id: str, *, active_only: bool = False
    ) -> tuple[Ticket, ...]:
        stmt = (
            select(TicketRecord)
            .where(TicketRecord.instance_id == instance_id)
            .order_by(TicketRecord.token_sequence)
        )
        if active_only:
            stmt = stmt.where(TicketRecord.state.notin_([s.value for s in CLOSED_STATES]))
        result = await self._session.execute(stmt)
        return tuple(ticket_from_row(r) for r in result.scalars().all())

    async def list_callable_tickets(self, instance_id: str) -> tuple[Ticket, ...]:
        """Candidate tickets, read without locking.

        The ordering decision needs to see the whole callable set — priority
        classes, appointment times, the intake-ready window — so the read is
        unlocked and the *chosen* row is locked afterwards by
        `claim_ticket`. Locking the whole set here instead would be safe but
        would serialise callers: the second practitioner would find every row
        locked and be told the queue was empty.
        """
        result = await self._session.execute(
            select(TicketRecord).where(
                TicketRecord.instance_id == instance_id,
                TicketRecord.state.in_(_CALLABLE_STATE_VALUES),
            )
        )
        return tuple(ticket_from_row(r) for r in result.scalars().all())

    async def claim_ticket(self, ticket_id: str) -> Ticket | None:
        """Lock one ticket for calling, or return None if someone else got it.

        `FOR UPDATE SKIP LOCKED` on a single row: a concurrent caller that has
        already locked this ticket causes an immediate miss rather than a wait,
        and the caller moves on to its next candidate. The state predicate is
        re-checked inside the lock, so a ticket called between the unlocked read
        and this claim is not called twice.
        """
        stmt = select(TicketRecord).where(
            TicketRecord.id == ticket_id,
            TicketRecord.state.in_(_CALLABLE_STATE_VALUES),
        )
        if self._supports_row_locking():
            stmt = stmt.with_for_update(skip_locked=True)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return None if row is None else ticket_from_row(row)

    async def increment_overtaken(self, ticket_ids: tuple[str, ...]) -> None:
        """Bump `overtaken_count` atomically in SQL.

        Read-modify-write in Python would lose increments when two callers pass
        the same waiting patient at once — and that counter is the starvation
        guard, so losing increments would let a patient be passed indefinitely.
        """
        if not ticket_ids:
            return
        await self._session.execute(
            update(TicketRecord)
            .where(TicketRecord.id.in_(ticket_ids))
            .values(overtaken_count=TicketRecord.overtaken_count + 1)
        )
        await self._session.flush()

    async def intake_states_for(self, tickets: tuple[Ticket, ...]) -> IntakeStateLookup:
        """Intake state for the tickets that have an intake.

        Read through a join rather than stored on the ticket, which is what keeps
        the two state machines orthogonal while still letting the ordering policy
        see readiness.
        """
        intake_ids = [str(t.intake_id) for t in tickets if t.intake_id is not None]
        if not intake_ids:
            return {}
        result = await self._session.execute(
            select(IntakeRecord.id, IntakeRecord.state).where(IntakeRecord.id.in_(intake_ids))
        )
        return {IntakeId(row[0]): IntakeState(row[1]) for row in result.all()}

    async def find_ticket_for_intake(self, intake_id: str) -> Ticket | None:
        result = await self._session.execute(
            select(TicketRecord)
            .where(TicketRecord.intake_id == intake_id)
            .where(TicketRecord.state.notin_([s.value for s in CLOSED_STATES]))
            .order_by(TicketRecord.issued_at.desc())
        )
        row = result.scalars().first()
        return None if row is None else ticket_from_row(row)

    async def waiting_snapshot(
        self, instance_id: str, *, now: datetime
    ) -> tuple[dict[str, object], ...]:
        """Dashboard payload for one instance.

        Carries `waiting_minutes` and `overtaken_count` per ticket, which is what
        makes the starvation guard visible to a human rather than merely enforced
        in code.
        """
        tickets = await self.list_tickets(instance_id, active_only=True)
        return tuple(
            {
                "ticket_id": str(t.ticket_id),
                "token": t.token_number,
                "priority_class": t.priority_class.value,
                "queue_state": t.state.value,
                "waiting_minutes": t.waiting_minutes(now),
                "overtaken_count": t.overtaken_count,
                "recall_count": t.recall_count,
                "has_intake": t.intake_id is not None,
            }
            for t in tickets
        )
