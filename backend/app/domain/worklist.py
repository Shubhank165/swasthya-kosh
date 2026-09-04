"""The worklist: an ordered list of intakes waiting for a doctor.

Minimal on purpose. `stale/queue/` holds a full OPD queue domain — priority
classes, recall, no-show accounting, overtake limits, shadow-mode reconciliation
with an HMIS — and none of it is rebuilt here. The problem statement does not ask
for queue management, the hospital already has one, and every line of queue code
is a line that has to agree with whatever the HMIS decides.

What is left is the one thing the dashboard actually needs: intakes for a
department, in arrival order, each with a status, and red-flag-pending surfaced
separately for a human to acknowledge.

Ordering is arrival time. It is not clinical triage and does not pretend to be:
a fired red-flag criterion does **not** move an intake up the list. It raises an
alert a person acknowledges, and that person decides what happens next. Software
that reorders a waiting room on its own reading of a symptom has made a triage
decision, and this system is not permitted to make one.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.record import IntakeStatus


class WorklistState(StrEnum):
    """What the dashboard shows against an intake."""

    #: Complete, no outstanding alert. The doctor can read it.
    READY = "ready"
    #: The interview did not finish. Shown with the rest marked unanswered —
    #: never hidden, because a partial history is still a history.
    PARTIAL = "partial"
    #: A red-flag criterion fired on the device and nobody has acknowledged it.
    RED_FLAG_PENDING = "red_flag_pending"
    #: Repair ran, or repair failed, or a value needs checking against a scan.
    NEEDS_REVIEW = "needs_review"
    #: A physician has seen it.
    SEEN = "seen"


class WorklistEntry(BaseModel):
    """One row.

    Identifiers, enums and counters only — no clinical text. This structure
    reaches a waiting-room-adjacent dashboard and the WebSocket feed behind it,
    and neither is a place a patient's history may appear.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    intake_id: str
    hospital_id: str
    department_code: str | None = None
    state: WorklistState
    intake_status: IntakeStatus
    arrived_at: datetime
    language: str = "en"
    #: How many red-flag events are still unacknowledged.
    unacknowledged_alerts: int = 0
    #: How many fields the device could not settle. A count, never the fields.
    unresolved_count: int = 0
    contradiction_count: int = 0
    needs_verification: bool = False
    repaired: bool = False
    patient_ref_type: str = "guest"
    seen_at: datetime | None = None

    @property
    def is_actionable(self) -> bool:
        """True when a human has something to do with this row."""
        return self.state in {WorklistState.RED_FLAG_PENDING, WorklistState.NEEDS_REVIEW}


class Worklist(BaseModel):
    """The ordered list, plus the alerts pulled out for acknowledgement."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department_code: str | None = None
    entries: tuple[WorklistEntry, ...] = ()
    #: The same rows that need acknowledging, surfaced separately so a
    #: dashboard cannot bury them by scrolling.
    pending_alerts: tuple[WorklistEntry, ...] = ()
    generated_at: datetime | None = None
    total: int = Field(default=0, ge=0)


def state_for(
    *,
    status: IntakeStatus,
    unacknowledged_alerts: int,
    seen_at: datetime | None,
    needs_review: bool,
) -> WorklistState:
    """The state one intake shows.

    Precedence, strongest first: a doctor has seen it; an alert is
    unacknowledged; something needs a human's eyes; the interview did not
    finish; otherwise ready.
    """
    if seen_at is not None:
        return WorklistState.SEEN
    if unacknowledged_alerts > 0:
        return WorklistState.RED_FLAG_PENDING
    if needs_review:
        return WorklistState.NEEDS_REVIEW
    if status in {IntakeStatus.PARTIAL, IntakeStatus.ABANDONED}:
        return WorklistState.PARTIAL
    return WorklistState.READY


def order(entries: Sequence[WorklistEntry]) -> tuple[WorklistEntry, ...]:
    """Arrival order, oldest first.

    `intake_id` breaks ties so the ordering is total and the list does not
    shuffle between polls when two kiosks submit in the same second.
    """
    return tuple(sorted(entries, key=lambda e: (e.arrived_at, e.intake_id)))


def assemble(
    entries: Sequence[WorklistEntry],
    *,
    department_code: str | None = None,
    generated_at: datetime | None = None,
) -> Worklist:
    """The worklist for a department."""
    ordered = order(entries)
    return Worklist(
        department_code=department_code,
        entries=ordered,
        pending_alerts=tuple(
            e for e in ordered if e.state is WorklistState.RED_FLAG_PENDING
        ),
        generated_at=generated_at,
        total=len(ordered),
    )
