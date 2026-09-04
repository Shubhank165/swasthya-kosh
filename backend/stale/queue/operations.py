"""Queue operations.

Every operation is a pure function: it takes the current entities plus an
explicitly supplied `now`, and returns the new entities and the events to
publish. Nothing here talks to a database, generates an id, or reads a clock —
the repository layer supplies all three and owns the row locking that makes
`call_next` safe under concurrency.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from app.domain.clinical.provenance import (
    AlertId,
    IntakeId,
    PatientId,
    QueueId,
    QueueInstanceId,
    TicketId,
    UserId,
)
from app.domain.queue.entities import (
    CLOSED_STATES,
    EscalationRecord,
    InstanceStatus,
    PriorityClass,
    Queue,
    QueueInstance,
    QueueState,
    Ticket,
    UnservedPolicy,
)
from app.domain.queue.ordering import IntakeStateLookup, Selection, select_next
from app.domain.queue.policies import DEFAULT_POLICIES, QueuePolicySet


class QueueOperationError(ValueError):
    """An operation was attempted that the queue rules forbid."""


@dataclass(frozen=True, slots=True)
class QueueEvent:
    """A domain event. The service layer maps these onto the event bus.

    `payload` carries identifiers and counters only — never clinical text, so
    these are safe to log and to fan out to a waiting-room display.
    """

    name: str
    ticket_id: TicketId | None = None
    instance_id: QueueInstanceId | None = None
    queue_id: QueueId | None = None
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OperationResult:
    """New entity states plus the events they produced."""

    ticket: Ticket | None = None
    instance: QueueInstance | None = None
    #: Tickets other than the primary one that changed — passed-over tickets on a
    #: call, carried-forward tickets on a close.
    affected_tickets: tuple[Ticket, ...] = field(default_factory=tuple)
    events: tuple[QueueEvent, ...] = field(default_factory=tuple)


def _require_open(instance: QueueInstance) -> None:
    if instance.status is InstanceStatus.CLOSED:
        raise QueueOperationError(f"queue instance {instance.instance_id} is closed")
    if instance.status is InstanceStatus.PAUSED:
        raise QueueOperationError(f"queue instance {instance.instance_id} is paused")


def issue(
    queue: Queue,
    instance: QueueInstance,
    *,
    ticket_id: TicketId,
    sequence: int,
    priority_class: PriorityClass,
    now: datetime,
    patient_id: PatientId | None = None,
    intake_id: IntakeId | None = None,
    appointment_slot_time: datetime | None = None,
    priority_reason: str | None = None,
) -> OperationResult:
    """Issue a token. `sequence` comes from the repository, which owns the counter."""
    _require_open(instance)
    if queue.capacity is not None and instance.counters.last_issued >= queue.capacity:
        raise QueueOperationError(
            f"queue {queue.queue_id} has reached its capacity of {queue.capacity}"
        )
    ticket = Ticket(
        ticket_id=ticket_id,
        queue_id=queue.queue_id,
        instance_id=instance.instance_id,
        token_number=queue.token_for(sequence),
        token_sequence=sequence,
        priority_class=priority_class,
        state=QueueState.WAITING,
        issued_at=now,
        patient_id=patient_id,
        intake_id=intake_id,
        appointment_slot_time=appointment_slot_time,
    )
    updated = replace(instance, counters=instance.counters.with_issue(sequence))
    return OperationResult(
        ticket=ticket,
        instance=updated,
        events=(
            QueueEvent(
                name="queue.ticket.issued",
                ticket_id=ticket_id,
                instance_id=instance.instance_id,
                queue_id=queue.queue_id,
                payload={
                    "token": ticket.token_number,
                    "priority_class": priority_class.value,
                    "priority_reason": priority_reason or "",
                },
            ),
        ),
    )


def call_next(
    queue: Queue,
    instance: QueueInstance,
    tickets: Sequence[Ticket],
    intake_states: IntakeStateLookup,
    *,
    now: datetime,
    practitioner_id: str | None = None,
    service_point: str | None = None,
) -> OperationResult | None:
    """Pick and call the next ticket, or return None when nothing is callable.

    The repository must hold `SELECT ... FOR UPDATE SKIP LOCKED` over the
    candidate rows across this call. This function is deterministic given its
    inputs; concurrency safety is the transaction's job, not the algorithm's.
    """
    _require_open(instance)
    selection = select_next(
        tickets,
        queue,
        instance,
        intake_states,
        practitioner_id=practitioner_id,
        service_point=service_point,
    )
    if selection is None:
        return None
    return _apply_call(queue, instance, selection, now=now)


def _apply_call(
    queue: Queue, instance: QueueInstance, selection: Selection, *, now: datetime
) -> OperationResult:
    called = replace(selection.ticket, state=QueueState.CALLED, called_at=now)
    passed = tuple(
        replace(t, overtaken_count=t.overtaken_count + 1) for t in selection.passed_over
    )
    updated = replace(instance, counters=instance.counters.with_call(called.token_number))
    events: list[QueueEvent] = [
        QueueEvent(
            name="queue.ticket.called",
            ticket_id=called.ticket_id,
            instance_id=instance.instance_id,
            queue_id=queue.queue_id,
            payload={
                "token": called.token_number,
                "selection_reason": selection.reason,
                "waiting_minutes": called.waiting_minutes(now),
                "passed_over": len(passed),
            },
        )
    ]
    events.extend(
        QueueEvent(
            name="queue.ticket.overtaken",
            ticket_id=t.ticket_id,
            instance_id=instance.instance_id,
            queue_id=queue.queue_id,
            payload={
                "token": t.token_number,
                "overtaken_count": t.overtaken_count,
                "max_overtaken": queue.max_overtaken,
            },
        )
        for t in passed
    )
    return OperationResult(
        ticket=called, instance=updated, affected_tickets=passed, events=tuple(events)
    )


def recall(
    queue: Queue,
    instance: QueueInstance,
    ticket: Ticket,
    *,
    now: datetime,
    policies: QueuePolicySet = DEFAULT_POLICIES,
) -> OperationResult:
    """Patient did not present when called. Re-insert, or mark NO_SHOW.

    Never a silent drop: a patient who missed a call because they were in the
    toilet gets two more chances, and the transition to NO_SHOW is an explicit
    recorded event.
    """
    if ticket.state not in {QueueState.CALLED, QueueState.RECALLED}:
        raise QueueOperationError(
            f"ticket {ticket.token_number} is {ticket.state}; only a called ticket can be recalled"
        )
    if policies.recall.exhausted(ticket.recall_count):
        return no_show(queue, instance, ticket, now=now)

    after = queue.recall_after_tokens or policies.recall.after_tokens
    recalled = replace(
        ticket,
        state=QueueState.RECALLED,
        recall_count=ticket.recall_count + 1,
        recall_sequence=ticket.effective_sequence + after,
        called_at=None,
        wait_credit_seconds=ticket.waiting_seconds(now),
    )
    updated = replace(instance, counters=instance.counters.with_requeue())
    return OperationResult(
        ticket=recalled,
        instance=updated,
        events=(
            QueueEvent(
                name="queue.ticket.recalled",
                ticket_id=ticket.ticket_id,
                instance_id=instance.instance_id,
                queue_id=queue.queue_id,
                payload={
                    "token": ticket.token_number,
                    "recall_count": recalled.recall_count,
                    "max_recalls": policies.recall.max_recalls,
                    "reinserted_after_tokens": after,
                },
            ),
        ),
    )


def start_consultation(
    queue: Queue, instance: QueueInstance, ticket: Ticket, *, now: datetime
) -> OperationResult:
    """Patient is with the practitioner."""
    if ticket.state not in {QueueState.CALLED, QueueState.RECALLED, QueueState.ESCALATED}:
        raise QueueOperationError(
            f"ticket {ticket.token_number} is {ticket.state}; call it before starting"
        )
    started = replace(ticket, state=QueueState.IN_CONSULTATION, started_at=now)
    return OperationResult(
        ticket=started,
        instance=instance,
        events=(
            QueueEvent(
                name="queue.ticket.started",
                ticket_id=ticket.ticket_id,
                instance_id=instance.instance_id,
                queue_id=queue.queue_id,
                payload={"token": ticket.token_number},
            ),
        ),
    )


def complete(
    queue: Queue, instance: QueueInstance, ticket: Ticket, *, now: datetime
) -> OperationResult:
    """Consultation finished. Folds the duration into the rolling service mean."""
    if ticket.state is not QueueState.IN_CONSULTATION:
        raise QueueOperationError(
            f"ticket {ticket.token_number} is {ticket.state}; only a consultation can complete"
        )
    duration = (now - ticket.started_at).total_seconds() if ticket.started_at else 0.0
    completed = replace(ticket, state=QueueState.COMPLETED, completed_at=now)
    updated = replace(instance, counters=instance.counters.with_completion(max(duration, 0.0)))
    return OperationResult(
        ticket=completed,
        instance=updated,
        events=(
            QueueEvent(
                name="queue.ticket.completed",
                ticket_id=ticket.ticket_id,
                instance_id=instance.instance_id,
                queue_id=queue.queue_id,
                payload={
                    "token": ticket.token_number,
                    "service_seconds": round(duration, 1),
                    "avg_service_seconds": updated.counters.avg_service_seconds,
                },
            ),
        ),
    )


def defer(
    queue: Queue,
    instance: QueueInstance,
    ticket: Ticket,
    *,
    now: datetime,
    reason: str | None = None,
) -> OperationResult:
    """Send the patient away and back — for a test, a payment, a Panchakarma slot.

    Priority class and accumulated wait are preserved, so a deferred senior
    citizen does not come back as a fresh walk-in.
    """
    if ticket.state in CLOSED_STATES:
        raise QueueOperationError(f"ticket {ticket.token_number} is {ticket.state}")
    deferred = replace(
        ticket,
        state=QueueState.DEFERRED,
        deferred_at=now,
        called_at=None,
        wait_credit_seconds=ticket.waiting_seconds(now),
    )
    counters = (
        instance.counters
        if ticket.state in {QueueState.WAITING, QueueState.ISSUED}
        else instance.counters.with_requeue()
    )
    return OperationResult(
        ticket=deferred,
        instance=replace(instance, counters=counters),
        events=(
            QueueEvent(
                name="queue.ticket.deferred",
                ticket_id=ticket.ticket_id,
                instance_id=instance.instance_id,
                queue_id=queue.queue_id,
                payload={
                    "token": ticket.token_number,
                    "reason": reason or "",
                    "wait_credit_seconds": round(deferred.wait_credit_seconds, 1),
                },
            ),
        ),
    )


def transfer(
    queue: Queue,
    instance: QueueInstance,
    ticket: Ticket,
    *,
    target_queue: Queue,
    target_instance: QueueInstance,
    new_ticket_id: TicketId,
    new_sequence: int,
    now: datetime,
) -> OperationResult:
    """Move the patient to another queue, carrying their intake with them.

    The intake is not re-run: the same `intake_id` follows the patient, because
    a history taken in the waiting room does not stop being true when the
    referral goes from Kayachikitsa to Shalya Tantra.
    """
    if ticket.state in CLOSED_STATES:
        raise QueueOperationError(f"ticket {ticket.token_number} is {ticket.state}")
    _require_open(target_instance)

    source = replace(
        ticket,
        state=QueueState.TRANSFERRED,
        transferred_to=target_queue.queue_id,
        completed_at=now,
    )
    moved = Ticket(
        ticket_id=new_ticket_id,
        queue_id=target_queue.queue_id,
        instance_id=target_instance.instance_id,
        token_number=target_queue.token_for(new_sequence),
        token_sequence=new_sequence,
        priority_class=ticket.priority_class,
        state=QueueState.WAITING,
        issued_at=now,
        patient_id=ticket.patient_id,
        intake_id=ticket.intake_id,
        appointment_slot_time=ticket.appointment_slot_time,
        wait_credit_seconds=ticket.waiting_seconds(now),
        transferred_from=ticket.queue_id,
        escalation=ticket.escalation,
    )
    return OperationResult(
        ticket=moved,
        instance=replace(
            target_instance, counters=target_instance.counters.with_issue(new_sequence)
        ),
        affected_tickets=(source,),
        events=(
            QueueEvent(
                name="queue.ticket.transferred",
                ticket_id=ticket.ticket_id,
                instance_id=instance.instance_id,
                queue_id=queue.queue_id,
                payload={
                    "token": ticket.token_number,
                    "to_queue_id": str(target_queue.queue_id),
                    "new_token": moved.token_number,
                    "intake_carried": ticket.intake_id is not None,
                },
            ),
        ),
    )


def escalate(
    queue: Queue,
    instance: QueueInstance,
    ticket: Ticket,
    *,
    alert_id: AlertId | None,
    acknowledged_by: UserId | None,
    acting_user_id: UserId | None,
    now: datetime,
    reason: str | None = None,
) -> OperationResult:
    """Raise a ticket's urgency because a human said to.

    Requires an acknowledged alert id and an acting user, and rejects the call
    without both. This is the mechanical guarantee behind "a red flag never
    auto-escalates a patient": there is no code path from `evaluate` to here.
    """
    if alert_id is None or acknowledged_by is None:
        raise QueueOperationError(
            "escalation requires an acknowledged red-flag alert id and its acknowledging user"
        )
    if acting_user_id is None:
        raise QueueOperationError("escalation requires an acting user id")
    if ticket.state in CLOSED_STATES:
        raise QueueOperationError(f"ticket {ticket.token_number} is {ticket.state}")

    escalated = replace(
        ticket,
        state=QueueState.ESCALATED,
        priority_class=PriorityClass.EMERGENCY,
        escalation=EscalationRecord(
            alert_id=alert_id,
            acknowledged_by=acknowledged_by,
            escalated_by=acting_user_id,
            escalated_at=now,
            reason=reason,
        ),
    )
    return OperationResult(
        ticket=escalated,
        instance=instance,
        events=(
            QueueEvent(
                name="queue.ticket.escalated",
                ticket_id=ticket.ticket_id,
                instance_id=instance.instance_id,
                queue_id=queue.queue_id,
                payload={
                    "token": ticket.token_number,
                    "alert_id": str(alert_id),
                    "acknowledged_by": str(acknowledged_by),
                    "escalated_by": str(acting_user_id),
                },
            ),
        ),
    )


def no_show(
    queue: Queue, instance: QueueInstance, ticket: Ticket, *, now: datetime
) -> OperationResult:
    """Patient did not present after their recalls were exhausted."""
    if ticket.state in CLOSED_STATES:
        raise QueueOperationError(f"ticket {ticket.token_number} is already {ticket.state}")
    marked = replace(ticket, state=QueueState.NO_SHOW, completed_at=now)
    return OperationResult(
        ticket=marked,
        instance=replace(instance, counters=instance.counters.with_no_show()),
        events=(
            QueueEvent(
                name="queue.ticket.no_show",
                ticket_id=ticket.ticket_id,
                instance_id=instance.instance_id,
                queue_id=queue.queue_id,
                payload={"token": ticket.token_number, "recall_count": ticket.recall_count},
            ),
        ),
    )


def cancel(
    queue: Queue,
    instance: QueueInstance,
    ticket: Ticket,
    *,
    now: datetime,
    reason: str,
) -> OperationResult:
    """Withdraw a ticket. Always carries a reason."""
    if ticket.state in CLOSED_STATES:
        raise QueueOperationError(f"ticket {ticket.token_number} is already {ticket.state}")
    cancelled = replace(
        ticket, state=QueueState.CANCELLED, completed_at=now, cancelled_reason=reason
    )
    return OperationResult(
        ticket=cancelled,
        instance=replace(instance, counters=instance.counters.with_departure()),
        events=(
            QueueEvent(
                name="queue.ticket.cancelled",
                ticket_id=ticket.ticket_id,
                instance_id=instance.instance_id,
                queue_id=queue.queue_id,
                payload={"token": ticket.token_number, "reason": reason},
            ),
        ),
    )


def pause(instance: QueueInstance, *, now: datetime, reason: str | None = None) -> OperationResult:
    """Pause the session — ward rounds, a break, an emergency elsewhere."""
    if instance.status is not InstanceStatus.OPEN:
        raise QueueOperationError(f"instance {instance.instance_id} is {instance.status}")
    paused = replace(instance, status=InstanceStatus.PAUSED, paused_at=now)
    return OperationResult(
        instance=paused,
        events=(
            QueueEvent(
                name="queue.instance.paused",
                instance_id=instance.instance_id,
                queue_id=instance.queue_id,
                payload={"reason": reason or ""},
            ),
        ),
    )


def resume(instance: QueueInstance, *, now: datetime) -> OperationResult:
    if instance.status is not InstanceStatus.PAUSED:
        raise QueueOperationError(f"instance {instance.instance_id} is not paused")
    resumed = replace(instance, status=InstanceStatus.OPEN, paused_at=None)
    return OperationResult(
        instance=resumed,
        events=(
            QueueEvent(
                name="queue.instance.resumed",
                instance_id=instance.instance_id,
                queue_id=instance.queue_id,
                payload={},
            ),
        ),
    )


def close_instance(
    queue: Queue,
    instance: QueueInstance,
    tickets: Sequence[Ticket],
    *,
    now: datetime,
    policies: QueuePolicySet = DEFAULT_POLICIES,
) -> OperationResult:
    """Close the session and dispose of unserved tickets by configured policy.

    There is no implicit disposal: a facility that has not chosen a policy gets
    CARRY_FORWARD, which keeps the patient in the system, rather than a silent
    cancellation.
    """
    if instance.status is InstanceStatus.CLOSED:
        raise QueueOperationError(f"instance {instance.instance_id} is already closed")

    unserved = [t for t in tickets if t.is_active and t.instance_id == instance.instance_id]
    policy = policies.closure.unserved
    affected: list[Ticket] = []
    events: list[QueueEvent] = []

    for ticket in unserved:
        if policy is UnservedPolicy.CANCEL:
            affected.append(
                replace(
                    ticket,
                    state=QueueState.CANCELLED,
                    completed_at=now,
                    cancelled_reason="session closed",
                )
            )
            events.append(
                QueueEvent(
                    name="queue.ticket.cancelled",
                    ticket_id=ticket.ticket_id,
                    instance_id=instance.instance_id,
                    queue_id=queue.queue_id,
                    payload={"token": ticket.token_number, "reason": "session closed"},
                )
            )
        else:
            # CARRY_FORWARD and REASSIGN both preserve the patient's wait credit;
            # the repository re-homes REASSIGN tickets onto the target instance.
            affected.append(
                replace(
                    ticket,
                    state=QueueState.DEFERRED,
                    deferred_at=now,
                    called_at=None,
                    wait_credit_seconds=ticket.waiting_seconds(now),
                )
            )
            events.append(
                QueueEvent(
                    name="queue.ticket.deferred",
                    ticket_id=ticket.ticket_id,
                    instance_id=instance.instance_id,
                    queue_id=queue.queue_id,
                    payload={
                        "token": ticket.token_number,
                        "reason": f"session closed: {policy.value}",
                        "reassign_to_queue_id": policies.closure.reassign_to_queue_id or "",
                    },
                )
            )

    closed = replace(instance, status=InstanceStatus.CLOSED, closed_at=now)
    events.append(
        QueueEvent(
            name="queue.instance.closed",
            instance_id=instance.instance_id,
            queue_id=queue.queue_id,
            payload={"unserved_policy": policy.value, "unserved_count": len(unserved)},
        )
    )
    return OperationResult(
        instance=closed, affected_tickets=tuple(affected), events=tuple(events)
    )


def open_instance(instance: QueueInstance, *, now: datetime) -> OperationResult:
    """Open today's run of a queue."""
    if instance.status is InstanceStatus.CLOSED:
        raise QueueOperationError(f"instance {instance.instance_id} is closed")
    opened = replace(instance, status=InstanceStatus.OPEN, opened_at=now)
    return OperationResult(
        instance=opened,
        events=(
            QueueEvent(
                name="queue.instance.opened",
                instance_id=instance.instance_id,
                queue_id=instance.queue_id,
                payload={
                    "service_date": instance.service_date.isoformat(),
                    "session": instance.session.value,
                },
            ),
        ),
    )
