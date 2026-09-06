"""When a question makes sense — §9.

Three-valued, and that is the whole design. A condition is not satisfied or
unsatisfied; it is satisfied, refused, or *not yet knowable*, and the three have
different consequences:

    YES      ask it
    NO       never ask it, and record why it does not apply
    UNKNOWN  not yet — the slot it depends on has not been filled

Collapsing UNKNOWN into NO is the bug that makes an adaptive questionnaire feel
broken: `fever.maximum_temperature` requires `fever.measured`, and evaluating
that before the patient has been asked whether they measured anything would
discard the temperature question permanently, one turn before it became
askable.

Collapsing it into YES is worse. "How high did your temperature get" asked of
somebody who never mentioned a fever is a question that invents a symptom by
asking about it, and patients answer questions they are asked.
"""

from __future__ import annotations

from enum import Enum

from app.questioning_agent.core.patient_state import PatientState
from app.questioning_agent.core.schemas import Condition


class Tri(Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


def evaluate(condition: Condition | None, state: PatientState) -> Tri:
    """Whether `condition` holds for `state`."""
    if condition is None:
        return Tri.YES

    if condition.all:
        return _all(condition, state)
    if condition.any:
        return _any(condition, state)
    if condition.domain_active is not None:
        return Tri.YES if condition.domain_active in state.active_domains else Tri.NO
    return _leaf(condition, state)


def _all(condition: Condition, state: PatientState) -> Tri:
    """Every part. One NO settles it; otherwise any UNKNOWN holds it open."""
    results = [evaluate(part, state) for part in condition.all]
    if Tri.NO in results:
        return Tri.NO
    if Tri.UNKNOWN in results:
        return Tri.UNKNOWN
    return Tri.YES


def _any(condition: Condition, state: PatientState) -> Tri:
    """One part is enough. A YES settles it even with unknowns beside it."""
    results = [evaluate(part, state) for part in condition.any]
    if Tri.YES in results:
        return Tri.YES
    if Tri.UNKNOWN in results:
        return Tri.UNKNOWN
    return Tri.NO


def _leaf(condition: Condition, state: PatientState) -> Tri:
    slot = condition.slot
    if slot is None:
        return Tri.YES

    if not state.knows(slot):
        return Tri.UNKNOWN

    value = state.value(slot)

    if condition.known is not None:
        return Tri.YES if condition.known else Tri.NO

    if condition.any_of:
        # A code set satisfies `any_of` when any member matches, which is what
        # makes "productive or both" work against a multi-select answer.
        if isinstance(value, (list, tuple, set)):
            return Tri.YES if set(condition.any_of) & {str(v) for v in value} else Tri.NO
        return Tri.YES if str(value) in condition.any_of else Tri.NO

    if condition.equals is not None:
        return Tri.YES if value == condition.equals else Tri.NO

    # `{slot: x}` with nothing else means "x is known", which the check above
    # has already established.
    return Tri.YES


def unmet_because(condition: Condition | None) -> tuple[str, ...]:
    """The slots a refused condition looked at.

    Recorded against a skipped question so the case can say *why* something does
    not apply rather than leaving a hole. "Not applicable" is a statement; an
    absence is not.
    """
    if condition is None:
        return ()
    if condition.all or condition.any:
        out: list[str] = []
        for part in (*condition.all, *condition.any):
            out.extend(unmet_because(part))
        return tuple(dict.fromkeys(out))
    if condition.slot:
        return (condition.slot,)
    if condition.domain_active:
        return (f"domain:{condition.domain_active}",)
    return ()


__all__ = ["Tri", "evaluate", "unmet_because"]
