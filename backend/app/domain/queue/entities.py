"""Queue entities.

An AYUSH tertiary institute runs many concurrent OPDs — departmental, chamber-
based, pooled, plus weekday speciality clinics — so the durable definition of a
queue is separated from today's run of it. The consultant on duty changes, a
session pauses for ward rounds, two queues merge for an afternoon: none of that
should edit the configured queue.

`IntakeState` and `QueueState` are orthogonal by construction. Nothing in this
module derives one from the other, and `WAITING + IN_PROGRESS` — a patient in
the queue who is part-way through their history — is the normal case, not an
inconsistency.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import StrEnum

from app.domain.clinical.provenance import (
    AlertId,
    IntakeId,
    PatientId,
    QueueId,
    QueueInstanceId,
    TicketId,
    UserId,
)


class QueueState(StrEnum):
    """Hospital-owned lifecycle of a token."""

    ISSUED = "issued"
    WAITING = "waiting"
    CALLED = "called"
    IN_CONSULTATION = "in_consultation"
    COMPLETED = "completed"
    RECALLED = "recalled"
    DEFERRED = "deferred"
    TRANSFERRED = "transferred"
    NO_SHOW = "no_show"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"


#: States in which a ticket is still owed a consultation.
ACTIVE_STATES: frozenset[QueueState] = frozenset(
    {
        QueueState.ISSUED,
        QueueState.WAITING,
        QueueState.CALLED,
        QueueState.RECALLED,
        QueueState.DEFERRED,
        QueueState.ESCALATED,
        QueueState.IN_CONSULTATION,
    }
)

#: States from which a ticket can be picked by `call_next`.
CALLABLE_STATES: frozenset[QueueState] = frozenset(
    {QueueState.ISSUED, QueueState.WAITING, QueueState.DEFERRED, QueueState.ESCALATED}
)

#: Terminal states.
CLOSED_STATES: frozenset[QueueState] = frozenset(
    {
        QueueState.COMPLETED,
        QueueState.NO_SHOW,
        QueueState.CANCELLED,
        QueueState.TRANSFERRED,
    }
)


class PriorityClass(StrEnum):
    """Ordering class. Membership rules are configured per facility."""

    EMERGENCY = "emergency"
    PRIORITY = "priority"
    APPOINTMENT = "appointment"
    WALKIN = "walkin"


#: Lower sorts first.
PRIORITY_RANK: dict[PriorityClass, int] = {
    PriorityClass.EMERGENCY: 0,
    PriorityClass.PRIORITY: 1,
    PriorityClass.APPOINTMENT: 2,
    PriorityClass.WALKIN: 3,
}


class AssignmentPolicy(StrEnum):
    """How `call_next` picks which tickets a caller may take."""

    PER_PRACTITIONER = "per_practitioner"
    PER_SERVICE_POINT = "per_service_point"
    POOLED_BY_DEPARTMENT = "pooled_by_department"


class SessionName(StrEnum):
    MORNING = "morning"
    EVENING = "evening"
    FULL_DAY = "full_day"


class InstanceStatus(StrEnum):
    OPEN = "open"
    PAUSED = "paused"
    CLOSED = "closed"


class UnservedPolicy(StrEnum):
    """What happens to tickets still waiting when an instance closes.

    There is no default that quietly discards patients: the facility must have
    configured one of these.
    """

    CARRY_FORWARD = "carry_forward"
    CANCEL = "cancel"
    REASSIGN = "reassign"


class QueueMode(StrEnum):
    """Who owns the queue.

    In `SHADOW`, a hospital HMIS issues encounters and tokens and MediKiosk owns
    only `IntakeState`; queue mutations arrive through the `HISAdapter`.
    """

    SOURCE_OF_TRUTH = "source_of_truth"
    SHADOW = "shadow"


@dataclass(frozen=True, slots=True)
class Department:
    """An OPD department, e.g. Kayachikitsa."""

    code: str
    name: str
    facility: str


@dataclass(frozen=True, slots=True)
class Queue:
    """The durable definition. Editing this is an administrative act."""

    queue_id: QueueId
    name: str
    department_code: str
    service_point: str
    assignment_policy: AssignmentPolicy
    token_prefix: str
    capacity: int | None = None
    #: Weekday numbers (Mon=0) the queue runs on. Empty means every day.
    schedule_days: tuple[int, ...] = field(default_factory=tuple)
    session: SessionName = SessionName.FULL_DAY
    #: Priority classes this queue honours, most-privileged first.
    priority_classes: tuple[PriorityClass, ...] = field(
        default_factory=lambda: (
            PriorityClass.EMERGENCY,
            PriorityClass.PRIORITY,
            PriorityClass.APPOINTMENT,
            PriorityClass.WALKIN,
        )
    )
    #: Off by default. When on, a READY intake may be taken ahead of an
    #: unprepared one within the same priority class and within `intake_ready_window`.
    prefer_intake_ready: bool = False
    intake_ready_window: int = 3
    #: Hard cap on how many times any one ticket may be passed over.
    max_overtaken: int = 3
    #: `recall` re-inserts the ticket this many tokens later.
    recall_after_tokens: int = 3
    max_recalls: int = 2
    unserved_policy: UnservedPolicy = UnservedPolicy.CARRY_FORWARD
    mode: QueueMode = QueueMode.SOURCE_OF_TRUTH

    def runs_on(self, day: date) -> bool:
        return not self.schedule_days or day.weekday() in self.schedule_days

    def token_for(self, sequence: int) -> str:
        return f"{self.token_prefix}-{sequence:03d}"


@dataclass(frozen=True, slots=True)
class QueueCounters:
    """Live counters for one instance."""

    last_issued: int = 0
    now_serving: str | None = None
    waiting_count: int = 0
    completed_count: int = 0
    no_show_count: int = 0
    #: Rolling mean consultation duration, seconds. None until one completes.
    avg_service_seconds: float | None = None
    served_sample: int = 0

    def with_issue(self, sequence: int) -> QueueCounters:
        return replace(
            self, last_issued=sequence, waiting_count=self.waiting_count + 1
        )

    def with_call(self, token: str) -> QueueCounters:
        return replace(
            self, now_serving=token, waiting_count=max(self.waiting_count - 1, 0)
        )

    def with_requeue(self) -> QueueCounters:
        return replace(self, waiting_count=self.waiting_count + 1)

    def with_completion(self, service_seconds: float) -> QueueCounters:
        """Fold a completed consultation into the rolling mean.

        A cumulative mean rather than a window: it is stable, needs no history,
        and an OPD session is short enough that drift is not a concern.
        """
        sample = self.served_sample + 1
        if self.avg_service_seconds is None:
            average = service_seconds
        else:
            delta = service_seconds - self.avg_service_seconds
            average = self.avg_service_seconds + delta / sample
        return replace(
            self,
            completed_count=self.completed_count + 1,
            avg_service_seconds=round(average, 2),
            served_sample=sample,
        )

    def with_no_show(self) -> QueueCounters:
        return replace(
            self,
            no_show_count=self.no_show_count + 1,
            waiting_count=max(self.waiting_count - 1, 0),
        )

    def with_departure(self) -> QueueCounters:
        """A waiting ticket left the queue without being served (cancel/transfer)."""
        return replace(self, waiting_count=max(self.waiting_count - 1, 0))


@dataclass(frozen=True, slots=True)
class QueueInstance:
    """Today's run of a queue."""

    instance_id: QueueInstanceId
    queue_id: QueueId
    service_date: date
    session: SessionName
    status: InstanceStatus = InstanceStatus.OPEN
    practitioner_id: UserId | None = None
    service_point: str | None = None
    counters: QueueCounters = field(default_factory=QueueCounters)
    opened_at: datetime | None = None
    paused_at: datetime | None = None
    closed_at: datetime | None = None
    #: Set when this instance was merged into another for the session.
    merged_into: QueueInstanceId | None = None

    @property
    def is_open(self) -> bool:
        return self.status is InstanceStatus.OPEN

    @property
    def accepts_calls(self) -> bool:
        return self.status is InstanceStatus.OPEN


@dataclass(frozen=True, slots=True)
class EscalationRecord:
    """Why and by whom a ticket was escalated.

    Both fields are mandatory: escalation is only ever the consequence of a human
    acknowledging a red flag, so there is always an alert and always an actor.
    """

    alert_id: AlertId
    acknowledged_by: UserId
    escalated_by: UserId
    escalated_at: datetime
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Ticket:
    """One patient's place in one queue."""

    ticket_id: TicketId
    queue_id: QueueId
    instance_id: QueueInstanceId
    token_number: str
    token_sequence: int
    priority_class: PriorityClass
    state: QueueState
    issued_at: datetime
    patient_id: PatientId | None = None
    intake_id: IntakeId | None = None
    appointment_slot_time: datetime | None = None
    called_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    recall_count: int = 0
    overtaken_count: int = 0
    escalation: EscalationRecord | None = None
    #: Wait already accrued before a defer or transfer, preserved across the move.
    wait_credit_seconds: float = 0.0
    #: Effective position for recall re-insertion; defaults to `token_sequence`.
    recall_sequence: int | None = None
    transferred_from: QueueId | None = None
    transferred_to: QueueId | None = None
    cancelled_reason: str | None = None
    deferred_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES

    @property
    def is_callable(self) -> bool:
        return self.state in CALLABLE_STATES

    @property
    def effective_sequence(self) -> int:
        """Sequence used for ordering; a recalled ticket sits later than its token."""
        return self.recall_sequence if self.recall_sequence is not None else self.token_sequence

    def waiting_seconds(self, now: datetime) -> float:
        """Total wait including credit carried over from a defer or transfer."""
        reference = self.called_at or now
        return self.wait_credit_seconds + max(
            (reference - self.issued_at).total_seconds(), 0.0
        )

    def waiting_minutes(self, now: datetime) -> float:
        return round(self.waiting_seconds(now) / 60.0, 1)
