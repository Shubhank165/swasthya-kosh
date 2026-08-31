"""Queue orchestration.

Thin by design: the domain decides, this layer loads, persists and publishes.

`call_next` is the operation that matters. It takes the candidate rows under
`FOR UPDATE SKIP LOCKED` before the domain picks one, which is what makes two
practitioners on a pooled queue receive different tokens rather than the same
one. The selection algorithm itself stays pure and testable in memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, QueueError
from app.core.ids import IdFactory, UuidIdFactory
from app.domain.clinical.provenance import AlertId, IntakeId, PatientId, TicketId, UserId
from app.domain.queue import operations as ops
from app.domain.queue.entities import (
    InstanceStatus,
    PriorityClass,
    Queue,
    QueueInstance,
    SessionName,
    Ticket,
)
from app.domain.queue.ordering import (
    estimated_wait_minutes,
    order,
    position_of,
)
from app.domain.queue.policies import (
    ClosurePolicy,
    PatientAttributes,
    PriorityPolicy,
    QueuePolicySet,
    RecallPolicy,
    honoured_classes,
)
from app.events.bus import EventBus
from app.events.schemas import Event, EventName
from app.repositories.alerts import AlertRepository
from app.repositories.queues import QueueRepository


@dataclass(frozen=True, slots=True)
class TicketView:
    """What a caller sees about a ticket, including its live position and wait."""

    ticket: Ticket
    position: int
    estimated_wait_minutes: int
    waiting_minutes: float


class QueueService:
    def __init__(
        self,
        *,
        queues: QueueRepository,
        alerts: AlertRepository,
        bus: EventBus,
        settings: Settings | None = None,
        clock: Clock | None = None,
        ids: IdFactory | None = None,
    ) -> None:
        self._queues = queues
        self._alerts = alerts
        self._bus = bus
        self._settings = settings or get_settings()
        self._clock = clock or SystemClock()
        self._ids = ids or UuidIdFactory()

    def _policies(self, queue: Queue) -> QueuePolicySet:
        """Policies for a queue: facility defaults, narrowed by queue config."""
        return QueuePolicySet(
            priority=PriorityPolicy(
                senior_citizen_age=self._settings.senior_citizen_age,
                infant_age_years=self._settings.infant_age_years,
            ),
            recall=RecallPolicy(
                after_tokens=queue.recall_after_tokens, max_recalls=queue.max_recalls
            ),
            closure=ClosurePolicy(unserved=queue.unserved_policy),
        )

    async def _publish(self, events: tuple[ops.QueueEvent, ...], *, department_code: str) -> None:
        now = self._clock.now()
        for event in events:
            try:
                name = EventName(event.name)
            except ValueError:
                continue
            await self._bus.publish(
                Event(
                    name=name,
                    occurred_at=now,
                    department_code=department_code,
                    ticket_id=str(event.ticket_id) if event.ticket_id else None,
                    queue_id=str(event.queue_id) if event.queue_id else None,
                    instance_id=str(event.instance_id) if event.instance_id else None,
                    payload=dict(event.payload),
                )
            )

    async def _commit(self, result: ops.OperationResult, queue: Queue) -> None:
        if result.instance is not None:
            await self._queues.save_instance(result.instance)
        if result.ticket is not None:
            existing = await self._queues.get_ticket(str(result.ticket.ticket_id))
            if existing is None:
                await self._queues.add_ticket(result.ticket)
            else:
                await self._queues.save_ticket(result.ticket)
        await self._queues.save_tickets(result.affected_tickets)
        await self._publish(result.events, department_code=queue.department_code)

    # --- instances ------------------------------------------------------------

    async def open_instance(
        self,
        queue_id: str,
        *,
        service_date: date,
        session: SessionName,
        practitioner_id: str | None = None,
        service_point: str | None = None,
    ) -> QueueInstance:
        """Open today's run, or return the one already open."""
        queue = await self._queues.require_queue(queue_id)
        existing = await self._queues.instance_for(
            queue_id, service_date=service_date, session_name=session.value
        )
        if existing is not None:
            return existing
        instance = QueueInstance(
            instance_id=self._ids.new_id("qi"),
            queue_id=queue.queue_id,
            service_date=service_date,
            session=session,
            status=InstanceStatus.OPEN,
            practitioner_id=UserId(practitioner_id) if practitioner_id else None,
            service_point=service_point or queue.service_point,
            opened_at=self._clock.now(),
        )
        created = await self._queues.create_instance(instance)
        await self._publish(
            ops.open_instance(created, now=self._clock.now()).events,
            department_code=queue.department_code,
        )
        return created

    async def pause(self, instance_id: str, *, reason: str | None = None) -> QueueInstance:
        instance = await self._queues.require_instance(instance_id)
        queue = await self._queues.require_queue(str(instance.queue_id))
        result = self._run(ops.pause, instance, now=self._clock.now(), reason=reason)
        await self._commit(result, queue)
        assert result.instance is not None
        return result.instance

    async def resume(self, instance_id: str) -> QueueInstance:
        instance = await self._queues.require_instance(instance_id)
        queue = await self._queues.require_queue(str(instance.queue_id))
        result = self._run(ops.resume, instance, now=self._clock.now())
        await self._commit(result, queue)
        assert result.instance is not None
        return result.instance

    async def close_instance(self, instance_id: str) -> QueueInstance:
        instance = await self._queues.require_instance(instance_id)
        queue = await self._queues.require_queue(str(instance.queue_id))
        tickets = await self._queues.list_tickets(instance_id, active_only=True)
        try:
            result = ops.close_instance(
                queue,
                instance,
                tickets,
                now=self._clock.now(),
                policies=self._policies(queue),
            )
        except ops.QueueOperationError as exc:
            raise QueueError(str(exc)) from exc
        await self._commit(result, queue)
        assert result.instance is not None
        return result.instance

    # --- tickets ---------------------------------------------------------------

    async def issue(
        self,
        queue_id: str,
        *,
        instance_id: str,
        attributes: PatientAttributes,
        patient_id: str | None = None,
        intake_id: str | None = None,
        appointment_slot_time: datetime | None = None,
        override_priority: PriorityClass | None = None,
    ) -> TicketView:
        """Issue a token.

        The sequence is reserved under a row lock on the instance before the
        domain builds the ticket, so two counters cannot produce the same number.
        """
        queue = await self._queues.require_queue(queue_id)
        instance = await self._queues.require_instance(instance_id)
        policies = self._policies(queue)
        priority, reason = policies.priority_for(attributes)
        if override_priority is not None:
            priority, reason = override_priority, "staff override"
        priority = honoured_classes(queue.priority_classes, priority)

        sequence = await self._queues.next_sequence(instance_id)
        try:
            result = ops.issue(
                queue,
                instance,
                ticket_id=TicketId(self._ids.new_id("tkt")),
                sequence=sequence,
                priority_class=priority,
                now=self._clock.now(),
                patient_id=PatientId(patient_id) if patient_id else None,
                intake_id=IntakeId(intake_id) if intake_id else None,
                appointment_slot_time=appointment_slot_time,
                priority_reason=reason,
            )
        except ops.QueueOperationError as exc:
            raise QueueError(str(exc)) from exc
        await self._commit(result, queue)
        assert result.ticket is not None
        return await self.ticket_view(str(result.ticket.ticket_id))

    async def call_next(
        self,
        instance_id: str,
        *,
        practitioner_id: str | None = None,
        service_point: str | None = None,
    ) -> TicketView | None:
        """Call the next patient, or None when nothing is callable.

        The candidate rows are locked SKIP LOCKED for the length of the
        transaction, so a concurrent caller sees a different candidate set and
        the same token can never be issued twice.
        """
        instance = await self._queues.require_instance(instance_id)
        queue = await self._queues.require_queue(str(instance.queue_id))
        tickets = await self._queues.lock_callable_tickets(instance_id)
        if not tickets:
            return None
        intake_states = await self._queues.intake_states_for(tickets)
        try:
            result = ops.call_next(
                queue,
                instance,
                tickets,
                intake_states,
                now=self._clock.now(),
                practitioner_id=practitioner_id,
                service_point=service_point,
            )
        except ops.QueueOperationError as exc:
            raise QueueError(str(exc)) from exc
        if result is None:
            return None
        await self._commit(result, queue)
        assert result.ticket is not None
        return await self.ticket_view(str(result.ticket.ticket_id))

    async def recall(self, ticket_id: str) -> TicketView:
        ticket, queue, instance = await self._load(ticket_id)
        try:
            result = ops.recall(
                queue, instance, ticket, now=self._clock.now(), policies=self._policies(queue)
            )
        except ops.QueueOperationError as exc:
            raise QueueError(str(exc)) from exc
        await self._commit(result, queue)
        return await self.ticket_view(ticket_id)

    async def start_consultation(self, ticket_id: str) -> TicketView:
        ticket, queue, instance = await self._load(ticket_id)
        return await self._simple(
            ops.start_consultation, ticket, queue, instance, ticket_id=ticket_id
        )

    async def complete(self, ticket_id: str) -> TicketView:
        ticket, queue, instance = await self._load(ticket_id)
        return await self._simple(ops.complete, ticket, queue, instance, ticket_id=ticket_id)

    async def no_show(self, ticket_id: str) -> TicketView:
        ticket, queue, instance = await self._load(ticket_id)
        return await self._simple(ops.no_show, ticket, queue, instance, ticket_id=ticket_id)

    async def defer(self, ticket_id: str, *, reason: str | None = None) -> TicketView:
        ticket, queue, instance = await self._load(ticket_id)
        try:
            result = ops.defer(queue, instance, ticket, now=self._clock.now(), reason=reason)
        except ops.QueueOperationError as exc:
            raise QueueError(str(exc)) from exc
        await self._commit(result, queue)
        return await self.ticket_view(ticket_id)

    async def cancel(self, ticket_id: str, *, reason: str) -> TicketView:
        ticket, queue, instance = await self._load(ticket_id)
        try:
            result = ops.cancel(queue, instance, ticket, now=self._clock.now(), reason=reason)
        except ops.QueueOperationError as exc:
            raise QueueError(str(exc)) from exc
        await self._commit(result, queue)
        return await self.ticket_view(ticket_id)

    async def transfer(
        self, ticket_id: str, *, target_queue_id: str, target_instance_id: str
    ) -> TicketView:
        """Move a patient to another queue, carrying their intake with them.

        Intake is not re-run: the same `intake_id` follows the ticket, because a
        history taken in the waiting room does not stop being true when the
        referral goes from Kayachikitsa to Shalya Tantra.
        """
        ticket, queue, instance = await self._load(ticket_id)
        target_queue = await self._queues.require_queue(target_queue_id)
        target_instance = await self._queues.require_instance(target_instance_id)
        sequence = await self._queues.next_sequence(target_instance_id)
        try:
            result = ops.transfer(
                queue,
                instance,
                ticket,
                target_queue=target_queue,
                target_instance=target_instance,
                new_ticket_id=TicketId(self._ids.new_id("tkt")),
                new_sequence=sequence,
                now=self._clock.now(),
            )
        except ops.QueueOperationError as exc:
            raise QueueError(str(exc)) from exc
        await self._commit(result, target_queue)
        assert result.ticket is not None
        return await self.ticket_view(str(result.ticket.ticket_id))

    async def escalate(
        self,
        ticket_id: str,
        *,
        alert_id: str,
        acting_user_id: str,
        reason: str | None = None,
    ) -> TicketView:
        """Escalate a ticket on the strength of an acknowledged red flag.

        The alert must exist and must already have been acknowledged by a human.
        There is no path from red-flag evaluation to this method: a machine
        cannot escalate a patient, only a person who has taken responsibility
        for the alert can.
        """
        alert = await self._alerts.get(alert_id)
        if alert is None:
            raise NotFoundError(f"alert {alert_id} not found", details={"alert_id": alert_id})
        if not alert.is_acknowledged:
            raise ForbiddenError(
                "escalation requires an acknowledged red-flag alert; acknowledge it first",
                details={"alert_id": alert_id},
            )
        ticket, queue, instance = await self._load(ticket_id)
        try:
            result = ops.escalate(
                queue,
                instance,
                ticket,
                alert_id=AlertId(alert_id),
                acknowledged_by=alert.acknowledged_by,
                acting_user_id=UserId(acting_user_id),
                now=self._clock.now(),
                reason=reason,
            )
        except ops.QueueOperationError as exc:
            raise QueueError(str(exc)) from exc
        await self._commit(result, queue)
        return await self.ticket_view(ticket_id)

    # --- views ------------------------------------------------------------------

    async def ticket_view(self, ticket_id: str) -> TicketView:
        ticket = await self._queues.require_ticket(ticket_id)
        instance = await self._queues.require_instance(str(ticket.instance_id))
        tickets = await self._queues.list_tickets(str(ticket.instance_id), active_only=True)
        now = self._clock.now()
        position = position_of(ticket, tickets)
        return TicketView(
            ticket=ticket,
            position=position,
            estimated_wait_minutes=estimated_wait_minutes(
                position,
                instance,
                default_service_seconds=self._settings.default_service_seconds,
            ),
            waiting_minutes=ticket.waiting_minutes(now),
        )

    async def dashboard(self, instance_id: str) -> dict[str, object]:
        """Payload the dashboard and the WebSocket hub fan out.

        Carries `waiting_minutes` and `overtaken_count` per ticket so the
        starvation guard is visible to a human, not only enforced in code.
        """
        instance = await self._queues.require_instance(instance_id)
        queue = await self._queues.require_queue(str(instance.queue_id))
        now = self._clock.now()
        tickets = await self._queues.list_tickets(instance_id, active_only=True)
        ordered = order(tickets)
        return {
            "instance_id": instance_id,
            "queue_id": str(queue.queue_id),
            "queue_name": queue.name,
            "department_code": queue.department_code,
            "status": instance.status.value,
            "service_date": instance.service_date.isoformat(),
            "session": instance.session.value,
            "now_serving": instance.counters.now_serving,
            "last_issued": instance.counters.last_issued,
            "waiting_count": instance.counters.waiting_count,
            "completed_count": instance.counters.completed_count,
            "no_show_count": instance.counters.no_show_count,
            "avg_service_seconds": instance.counters.avg_service_seconds,
            "prefer_intake_ready": queue.prefer_intake_ready,
            "tickets": [
                {
                    "ticket_id": str(t.ticket_id),
                    "token": t.token_number,
                    "position": index,
                    "priority_class": t.priority_class.value,
                    "queue_state": t.state.value,
                    "waiting_minutes": t.waiting_minutes(now),
                    "overtaken_count": t.overtaken_count,
                    "recall_count": t.recall_count,
                    "has_intake": t.intake_id is not None,
                    "estimated_wait_minutes": estimated_wait_minutes(
                        index,
                        instance,
                        default_service_seconds=self._settings.default_service_seconds,
                    ),
                }
                for index, t in enumerate(ordered, start=1)
            ],
        }

    # --- internals ---------------------------------------------------------------

    async def _load(self, ticket_id: str) -> tuple[Ticket, Queue, QueueInstance]:
        ticket = await self._queues.require_ticket(ticket_id)
        queue = await self._queues.require_queue(str(ticket.queue_id))
        instance = await self._queues.require_instance(str(ticket.instance_id))
        return ticket, queue, instance

    def _run(self, operation, *args, **kwargs) -> ops.OperationResult:  # type: ignore[no-untyped-def]
        try:
            return operation(*args, **kwargs)
        except ops.QueueOperationError as exc:
            raise QueueError(str(exc)) from exc

    async def _simple(
        self,
        operation,  # type: ignore[no-untyped-def]
        ticket: Ticket,
        queue: Queue,
        instance: QueueInstance,
        *,
        ticket_id: str,
    ) -> TicketView:
        try:
            result = operation(queue, instance, ticket, now=self._clock.now())
        except ops.QueueOperationError as exc:
            raise QueueError(str(exc)) from exc
        await self._commit(result, queue)
        return await self.ticket_view(ticket_id)


def require_shadow_mode_guard(settings: Settings, action: str) -> None:
    """Reject queue mutations MediKiosk does not own in SHADOW mode.

    In SHADOW the hospital HMIS issues tokens and owns queue state; MediKiosk
    owns only `IntakeState`. Silently accepting a write here would put the two
    systems out of step, which is worse than refusing it.
    """
    if settings.is_shadow_mode:
        raise ConflictError(
            f"'{action}' is owned by the hospital HMIS while QUEUE_MODE is shadow",
            details={"queue_mode": settings.queue_mode},
        )
