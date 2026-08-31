"""Facility-configurable queue policies.

Who counts as `PRIORITY` is a facility decision, not a hard-coded one: the age
at which a patient is a senior citizen differs between institutions and states.
This module holds that configuration and the deterministic classifier that
applies it, so an audit can answer "why was this patient prioritised?" with a
rule id rather than a shrug.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.domain.queue.entities import PriorityClass, UnservedPolicy


@dataclass(frozen=True, slots=True)
class PatientAttributes:
    """The minimum needed to classify priority. Nothing clinical."""

    age_years: float | None = None
    is_pregnant: bool = False
    is_differently_abled: bool = False
    has_appointment: bool = False
    is_staff_referred_emergency: bool = False


@dataclass(frozen=True, slots=True)
class PriorityPolicy:
    """Facility rules for priority classification."""

    senior_citizen_age: float = 60.0
    infant_age_years: float = 2.0
    prioritise_pregnancy: bool = True
    prioritise_differently_abled: bool = True
    #: Extra concepts a facility wants prioritised, applied by staff at issue time.
    additional_priority_reasons: tuple[str, ...] = field(default_factory=tuple)

    def classify(self, attributes: PatientAttributes) -> tuple[PriorityClass, str]:
        """(class, reason). The reason is stored on the ticket's audit record.

        Emergency here means a human said so at the counter. A red flag never
        reaches this function: it produces an alert, and only an acknowledged
        alert can escalate a ticket.
        """
        if attributes.is_staff_referred_emergency:
            return PriorityClass.EMERGENCY, "staff-referred emergency"
        if self.prioritise_pregnancy and attributes.is_pregnant:
            return PriorityClass.PRIORITY, "pregnancy"
        if self.prioritise_differently_abled and attributes.is_differently_abled:
            return PriorityClass.PRIORITY, "differently-abled"
        if attributes.age_years is not None:
            if attributes.age_years >= self.senior_citizen_age:
                return (
                    PriorityClass.PRIORITY,
                    f"senior citizen (age ≥ {self.senior_citizen_age:g})",
                )
            if attributes.age_years <= self.infant_age_years:
                return PriorityClass.PRIORITY, f"infant (age ≤ {self.infant_age_years:g})"
        if attributes.has_appointment:
            return PriorityClass.APPOINTMENT, "booked appointment"
        return PriorityClass.WALKIN, "walk-in"


@dataclass(frozen=True, slots=True)
class RecallPolicy:
    """How a called-but-absent patient is retried.

    A ticket is never dropped silently: it is re-inserted `after_tokens` later,
    up to `max_recalls` times, and only then marked NO_SHOW.
    """

    after_tokens: int = 3
    max_recalls: int = 2

    def exhausted(self, recall_count: int) -> bool:
        return recall_count >= self.max_recalls


@dataclass(frozen=True, slots=True)
class ClosurePolicy:
    """What `close_instance` does with tickets still waiting."""

    unserved: UnservedPolicy = UnservedPolicy.CARRY_FORWARD
    #: Required when `unserved` is REASSIGN.
    reassign_to_queue_id: str | None = None

    def __post_init__(self) -> None:
        if self.unserved is UnservedPolicy.REASSIGN and not self.reassign_to_queue_id:
            raise ValueError("REASSIGN closure policy requires reassign_to_queue_id")


@dataclass(frozen=True, slots=True)
class QueuePolicySet:
    """Everything the queue operations need beyond the entities themselves."""

    priority: PriorityPolicy = field(default_factory=PriorityPolicy)
    recall: RecallPolicy = field(default_factory=RecallPolicy)
    closure: ClosurePolicy = field(default_factory=ClosurePolicy)

    def priority_for(self, attributes: PatientAttributes) -> tuple[PriorityClass, str]:
        return self.priority.classify(attributes)


DEFAULT_POLICIES = QueuePolicySet()


def honoured_classes(
    configured: Sequence[PriorityClass], requested: PriorityClass
) -> PriorityClass:
    """Downgrade a class the queue does not honour to WALKIN.

    A speciality clinic that does not take appointments must not silently order
    an appointment ticket ahead of everyone.
    """
    return requested if requested in configured else PriorityClass.WALKIN
