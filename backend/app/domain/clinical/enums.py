"""Clinical enumerations shared across the record, the report and the ontology.

Every enum here is a clinical distinction, not an implementation detail.

The field-status vocabulary lives in `app.domain.record` rather than here,
because it arrives from the kiosk and is versioned with the canonical record.
"""

from __future__ import annotations

from enum import StrEnum


class ReporterRole(StrEnum):
    """Who supplied the fact.

    An attendant-reported history is weaker evidence than a self-reported one and
    the physician must be able to see which.
    """

    SELF = "self"
    PARENT_GUARDIAN = "parent_guardian"
    FAMILY_ATTENDANT = "family_attendant"
    CAREGIVER = "caregiver"
    STAFF = "staff"


class Certainty(StrEnum):
    """How firmly the reporter committed to the value.

    `"maybe two weeks"` is APPROXIMATE and must stay APPROXIMATE. Nothing in the
    pipeline may promote certainty except a physician, explicitly.
    """

    CONFIRMED = "confirmed"
    REPORTED = "reported"
    APPROXIMATE = "approximate"
    UNCERTAIN = "uncertain"


#: Ordered weakest -> strongest. Used to assert that no transformation increases
#: certainty; see `certainty_rank`.
_CERTAINTY_ORDER: tuple[Certainty, ...] = (
    Certainty.UNCERTAIN,
    Certainty.APPROXIMATE,
    Certainty.REPORTED,
    Certainty.CONFIRMED,
)


def certainty_rank(certainty: Certainty) -> int:
    """Position of `certainty` on the weak->strong scale."""
    return _CERTAINTY_ORDER.index(certainty)


class RedFlagSeverity(StrEnum):
    """How serious the device judged a fired criterion to be.

    Two values, because the clinical content emits two: `critical` on five
    rules and `high` on four. This is not a scale to be extended casually — it
    decides who overtakes whom in a waiting room.

    **`CRITICAL` is the only value that reorders the queue.** A `HIGH` flag
    still raises an alert a clinician must acknowledge and still marks the
    intake on the worklist; it does not move the patient in front of anyone.
    Decision 79 has the argument.
    """

    CRITICAL = "critical"
    HIGH = "high"

    @classmethod
    def parse(cls, raw: object) -> RedFlagSeverity:
        """A severity from the wire, failing to the tier that does *not* jump.

        An unrecognised value becomes `HIGH`, never `CRITICAL`. The direction
        matters more than the default: a device sending a value this build has
        never heard of must not be able to reorder a waiting room by sending
        garbage, and the safe failure is the one that leaves the queue alone.
        The alert still fires either way, so nothing is hidden by this — only
        the overtaking is withheld.
        """
        try:
            return cls(str(raw).strip().lower())
        except ValueError:
            return cls.HIGH


class Section(StrEnum):
    """Sections of the history, in the clinical order it is taken.

    The order is fixed by the spec and is the render order of the
    report — see `SECTION_ORDER`.
    """

    IDENTITY = "identity"
    CHIEF_COMPLAINT = "chief_complaint"
    HPI = "hpi"
    PAST_MEDICAL = "past_medical"
    PAST_SURGICAL = "past_surgical"
    MEDICATIONS = "medications"
    ALLERGIES = "allergies"
    FAMILY_HISTORY = "family_history"
    PERSONAL_HISTORY = "personal_history"
    REVIEW_OF_SYSTEMS = "review_of_systems"
    INVESTIGATIONS = "investigations"
    #: Screening answers the Jetson collected alongside its red-flag criteria.
    RED_FLAG_SCREEN = "red_flag_screen"
    CONSENT = "consent"


#: Canonical section order. The report renders in exactly this sequence.
SECTION_ORDER: tuple[Section, ...] = (
    Section.IDENTITY,
    Section.CHIEF_COMPLAINT,
    Section.HPI,
    Section.PAST_MEDICAL,
    Section.PAST_SURGICAL,
    Section.MEDICATIONS,
    Section.ALLERGIES,
    Section.FAMILY_HISTORY,
    Section.PERSONAL_HISTORY,
    Section.REVIEW_OF_SYSTEMS,
    Section.INVESTIGATIONS,
    Section.RED_FLAG_SCREEN,
    Section.CONSENT,
)


def section_rank(section: Section) -> int:
    """Position of `section` in the canonical order."""
    return SECTION_ORDER.index(section)


class Severity(StrEnum):
    """Red-flag severity. Ordering matters for alert presentation."""

    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"


_SEVERITY_ORDER: tuple[Severity, ...] = (Severity.MODERATE, Severity.HIGH, Severity.CRITICAL)


def severity_rank(severity: Severity) -> int:
    """Position of `severity` on the low->high scale."""
    return _SEVERITY_ORDER.index(severity)
