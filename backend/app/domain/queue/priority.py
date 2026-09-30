"""Which patient the doctor is offered next, and why.

`app/domain/worklist.py` used to order on arrival time alone, and said so at
length: software that reorders a waiting room on its own reading of a symptom
has made a triage decision. That reading has been reversed deliberately — see
decision 77 — and this module is where the reversal is confined.

Three properties make the reversal defensible, and losing any one of them
should be treated as breaking the feature rather than tuning it:

**No model decides.** The rules below are hand-written, ordered, and total.
The same intake produces the same class on every evaluation, on any machine,
for ever. A probabilistic priority is one nobody can answer a complaint about.

**Only what the device already decided.** `EMERGENCY` follows from a *critical*
red-flag criterion the Jetson fired during the interview and a human has not
yet acknowledged, or from the interview being cut short by one. This module
reads that outcome; it does not re-derive it from symptoms, and it has no
access to clinical text with which to try. A second opinion that disagrees with
the first is worse than no second opinion.

**And only the severe ones.** Every fired criterion used to overtake, because
this module counted alerts rather than reading them. It now reads their
severity, and only `critical` moves anybody. Decision 79 has the argument and
the objection against it.

**Escalation only.** A rule may move an intake up. Nothing here moves one down:
`WALKIN` is the floor, it is where everyone starts, and a patient cannot be
demoted below the position their arrival time earns them. That bound is what
stops a scoring change from quietly pushing somebody to the back of a queue
they had already waited in.

The vocabulary is `stale/queue/entities.py`'s, unchanged — the same four
classes and the same ranks, because a facility that configures membership
rules against them should not have to learn new words when the rest of that
queue domain comes back.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from app.domain.clinical.enums import RedFlagSeverity
from app.domain.record import IntakeStatus


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


def priority_for(
    *,
    status: IntakeStatus,
    unacknowledged_severities: Sequence[RedFlagSeverity],
    seen_at: object | None = None,
) -> PriorityClass:
    """The class one intake sorts in.

    Ordered, strongest first, and every branch is a fact the device or a
    physician already established:

    1. Seen. A patient the doctor has already read drops to the floor — not
       because they matter less, but because they are no longer waiting, and
       leaving them at the top would hold the front of the list for ever.
    2. An unacknowledged **critical** red-flag event. This is the emergency
       fast lane, and it is the device's finding, not this module's. A `high`
       flag is still a flag — it raises an alert, it marks the intake, a
       clinician still has to acknowledge it — and it does not move the
       patient in front of anybody who arrived first.
    3. The interview stopped because a criterion fired. The same finding
       arriving by a different route: the Jetson cut the intake short rather
       than finishing it, which it only does for a red flag.
    4. Everything else waits its turn.

    `PRIORITY` and `APPOINTMENT` are declared and ranked but never returned
    here. They are the classes a facility assigns — a booked slot, a category
    the hospital operates — and nothing in an intake record establishes either.
    Returning them from a guess would be this module inventing a status the
    hospital owns.
    """

    if seen_at is not None:
        return PriorityClass.WALKIN
    if any(s is RedFlagSeverity.CRITICAL for s in unacknowledged_severities):
        return PriorityClass.EMERGENCY
    if status is IntakeStatus.ABORTED_RED_FLAG:
        # No severity of its own to read. The device stops an interview only
        # for a criterion it judged serious enough to stop for, and a patient
        # the machine refused to keep questioning is not one to leave in
        # arrival order on the strength of a missing field.
        return PriorityClass.EMERGENCY
    return PriorityClass.WALKIN
