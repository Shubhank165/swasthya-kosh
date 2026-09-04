"""Queue API DTOs.

`IntakeState` and `QueueState` appear as separate fields on `TicketOut` and
neither is computed from the other, which is invariant 8 made visible at the
API boundary.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.domain.clinical.enums import IntakeState
from app.domain.queue.entities import (
    AssignmentPolicy,
    InstanceStatus,
    PriorityClass,
    QueueState,
    SessionName,
    UnservedPolicy,
)
from app.schemas.common import ApiModel


class DepartmentOut(ApiModel):
    code: str
    name: str
    facility: str


class QueueOut(ApiModel):
    queue_id: str
    name: str
    department_code: str
    service_point: str
    assignment_policy: AssignmentPolicy
    token_prefix: str
    capacity: int | None = None
    session: SessionName
    prefer_intake_ready: bool
    intake_ready_window: int
    max_overtaken: int
    unserved_policy: UnservedPolicy
    mode: str


class CountersOut(ApiModel):
    last_issued: int
    now_serving: str | None = None
    waiting_count: int
    completed_count: int
    no_show_count: int
    avg_service_seconds: float | None = None


class QueueInstanceOut(ApiModel):
    instance_id: str
    queue_id: str
    service_date: date
    session: SessionName
    status: InstanceStatus
    practitioner_id: str | None = None
    service_point: str | None = None
    counters: CountersOut


class OpenInstanceRequest(ApiModel):
    service_date: date | None = None
    session: SessionName = SessionName.FULL_DAY
    practitioner_id: str | None = None
    service_point: str | None = None


class IssueTicketRequest(ApiModel):
    instance_id: str
    patient_id: str | None = None
    intake_id: str | None = None
    appointment_slot_time: datetime | None = None
    age_years: float | None = None
    is_pregnant: bool = False
    is_differently_abled: bool = False
    has_appointment: bool = False
    #: Set by a staff member at the counter, never by a red flag.
    is_staff_referred_emergency: bool = False
    override_priority: PriorityClass | None = None


class TicketOut(ApiModel):
    ticket_id: str
    queue_id: str
    instance_id: str
    token_number: str
    token_sequence: int
    priority_class: PriorityClass
    #: Hospital-owned. Orthogonal to `intake_state`.
    queue_state: QueueState
    #: MediKiosk-owned. Null when the patient never touched a kiosk — which is a
    #: perfectly normal walk-in, not an error.
    intake_state: IntakeState | None = None
    patient_id: str | None = None
    intake_id: str | None = None
    issued_at: datetime
    called_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    recall_count: int
    overtaken_count: int
    position: int
    estimated_wait_minutes: int
    waiting_minutes: float
    escalation_alert_id: str | None = None


class DeferRequest(ApiModel):
    reason: str | None = None


class CancelRequest(ApiModel):
    reason: str


class TransferRequest(ApiModel):
    target_queue_id: str
    target_instance_id: str


class EscalateRequest(ApiModel):
    """Escalation requires both an acknowledged alert and an acting user.

    The API rejects the call without either, mirroring the domain, so a client
    cannot escalate a patient on a machine's say-so.
    """

    alert_id: str
    acting_user_id: str
    reason: str | None = None


class PauseRequest(ApiModel):
    reason: str | None = None


class DashboardOut(ApiModel):
    instance_id: str
    queue_id: str
    queue_name: str
    department_code: str
    status: str
    service_date: str
    session: str
    now_serving: str | None = None
    last_issued: int
    waiting_count: int
    completed_count: int
    no_show_count: int
    avg_service_seconds: float | None = None
    prefer_intake_ready: bool
    tickets: list[dict] = Field(default_factory=list)
