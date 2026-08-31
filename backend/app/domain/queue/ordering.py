"""Queue ordering.

Strict precedence: priority class, then appointment slot time, then token
sequence. `PREFER_INTAKE_READY` is the single deliberate deviation, and it is
bounded in three ways at once — same priority class only, within ±N positions
only, and capped per ticket — so no patient can be displaced indefinitely by a
stream of better-prepared arrivals.

Everything here is pure. Intake readiness arrives as a lookup rather than a
field on `Ticket`, which is what keeps intake state and queue state orthogonal.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.domain.clinical.enums import IntakeState
from app.domain.clinical.provenance import IntakeId
from app.domain.queue.entities import (
    PRIORITY_RANK,
    AssignmentPolicy,
    Queue,
    QueueInstance,
    Ticket,
)

#: Intake states that count as "prepared" for `PREFER_INTAKE_READY`.
READY_INTAKE_STATES: frozenset[IntakeState] = frozenset(
    {IntakeState.READY, IntakeState.SYNCED}
)

IntakeStateLookup = Mapping[IntakeId, IntakeState]

#: Sorts after every real appointment time, so walk-ins never displace a booked slot.
_NO_APPOINTMENT = datetime.max


def base_sort_key(ticket: Ticket) -> tuple[int, datetime, int]:
    """The strict clinical ordering key."""
    return (
        PRIORITY_RANK[ticket.priority_class],
        ticket.appointment_slot_time or _NO_APPOINTMENT,
        ticket.effective_sequence,
    )


def order(tickets: Sequence[Ticket]) -> tuple[Ticket, ...]:
    """Callable tickets in strict order, ignoring intake readiness."""
    return tuple(sorted((t for t in tickets if t.is_callable), key=base_sort_key))


def is_ready(ticket: Ticket, intake_states: IntakeStateLookup) -> bool:
    """True when this ticket's intake is finished and usable by the physician."""
    if ticket.intake_id is None:
        return False
    return intake_states.get(ticket.intake_id) in READY_INTAKE_STATES


def eligible_for(
    tickets: Sequence[Ticket],
    queue: Queue,
    instance: QueueInstance,
    *,
    practitioner_id: str | None = None,
    service_point: str | None = None,
) -> tuple[Ticket, ...]:
    """Tickets this caller may take, per the queue's assignment policy.

    One code path for all three policies; the policy only narrows the candidate
    set. Everything downstream — ordering, readiness preference, starvation
    guard — is identical whichever policy is in force.
    """
    candidates = [t for t in tickets if t.is_callable and t.instance_id == instance.instance_id]

    if queue.assignment_policy is AssignmentPolicy.PER_PRACTITIONER:
        if practitioner_id is None or instance.practitioner_id != practitioner_id:
            return ()
    elif queue.assignment_policy is AssignmentPolicy.PER_SERVICE_POINT:
        point = instance.service_point or queue.service_point
        if service_point is not None and service_point != point:
            return ()
    # POOLED_BY_DEPARTMENT: any caller on the instance may take any ticket.

    return order(candidates)


@dataclass(frozen=True, slots=True)
class Selection:
    """The chosen ticket, the tickets it passed, and why.

    `passed_over` is not diagnostic detail — those tickets each get their
    `overtaken_count` incremented, which is what bounds the whole mechanism.
    """

    ticket: Ticket
    passed_over: tuple[Ticket, ...] = ()
    reason: str = "strict order"

    @property
    def used_intake_preference(self) -> bool:
        return bool(self.passed_over)


def select_next(
    tickets: Sequence[Ticket],
    queue: Queue,
    instance: QueueInstance,
    intake_states: IntakeStateLookup,
    *,
    practitioner_id: str | None = None,
    service_point: str | None = None,
) -> Selection | None:
    """The ticket to call next, or None when nothing is callable.

    With `prefer_intake_ready` off this is simply the head of the strict order.
    With it on, the head is still taken unless it is unprepared *and* a prepared
    ticket sits within the window in the same priority class *and* none of the
    tickets that would be passed has already hit its overtaken cap.
    """
    ordered = eligible_for(
        tickets,
        queue,
        instance,
        practitioner_id=practitioner_id,
        service_point=service_point,
    )
    if not ordered:
        return None

    head = ordered[0]
    if not queue.prefer_intake_ready or is_ready(head, intake_states):
        return Selection(ticket=head, reason="strict order")

    window = ordered[1 : 1 + max(queue.intake_ready_window, 0)]
    for index, candidate in enumerate(window):
        if candidate.priority_class is not head.priority_class:
            break
        if not is_ready(candidate, intake_states):
            continue
        passed = (head, *window[:index])
        if any(t.overtaken_count >= queue.max_overtaken for t in passed):
            # Starvation guard: someone in the way has already been passed the
            # maximum number of times, so the preference yields to them.
            break
        return Selection(
            ticket=candidate,
            passed_over=passed,
            reason=(
                f"prefer_intake_ready: intake READY, {len(passed)} ticket(s) passed "
                f"within window {queue.intake_ready_window}"
            ),
        )

    return Selection(ticket=head, reason="strict order (no prepared ticket within window)")


def position_of(
    ticket: Ticket, tickets: Sequence[Ticket]
) -> int:
    """1-indexed position of `ticket` in the strict order, or 0 if not callable."""
    ordered = order(tickets)
    for index, candidate in enumerate(ordered, start=1):
        if candidate.ticket_id == ticket.ticket_id:
            return index
    return 0


#: Used until enough consultations have completed to compute a real mean. A
#: guessed wait is better than no wait shown, but it must be conservative.
DEFAULT_SERVICE_SECONDS = 8 * 60.0


def estimated_wait_seconds(
    position: int,
    instance: QueueInstance,
    *,
    default_service_seconds: float = DEFAULT_SERVICE_SECONDS,
) -> float:
    """Expected wait for a ticket at 1-indexed `position`.

    Shown to the patient on the kiosk, because "about 22 minutes — enough time to
    record your history" is what actually gets people to use it.
    """
    if position <= 0:
        return 0.0
    average = instance.counters.avg_service_seconds or default_service_seconds
    return round((position - 1) * average, 1)


def estimated_wait_minutes(
    position: int,
    instance: QueueInstance,
    *,
    default_service_seconds: float = DEFAULT_SERVICE_SECONDS,
) -> int:
    """Whole minutes, rounded to the nearest minute and never negative."""
    seconds = estimated_wait_seconds(
        position, instance, default_service_seconds=default_service_seconds
    )
    return max(round(seconds / 60.0), 0)
