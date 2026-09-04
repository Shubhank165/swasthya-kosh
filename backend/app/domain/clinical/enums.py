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


class Section(StrEnum):
    """Sections of the history, in the clinical order it is taken.

    The order is fixed by the problem statement and is the render order of the
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
    AYURVEDA = "ayurveda"
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
    Section.AYURVEDA,
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
