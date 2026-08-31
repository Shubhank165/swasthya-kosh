"""Clinical enumerations.

Every enum here is a clinical distinction, not an implementation detail. In
particular `FactStatus` has five members and none of them may ever be collapsed
into a boolean: "we did not ask" and "the patient said no" are different facts
with different medico-legal weight.
"""

from __future__ import annotations

from enum import StrEnum


class FactStatus(StrEnum):
    """Whether a clinical concept is affirmed, denied, or simply unestablished."""

    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"
    NOT_ASKED = "not_asked"
    NOT_APPLICABLE = "not_applicable"


#: Statuses that mean the question has actually been put to the patient and
#: settled. `UNKNOWN` counts: "I don't know" is an answer.
ANSWERED_STATUSES: frozenset[FactStatus] = frozenset(
    {FactStatus.PRESENT, FactStatus.ABSENT, FactStatus.UNKNOWN}
)


class SourceType(StrEnum):
    """Where a fact physically came from."""

    VOICE = "voice"
    TOUCH = "touch"
    DOCUMENT = "document"
    PRIOR_RECORD = "prior_record"
    STAFF = "staff"
    DERIVED = "derived"


class Temporality(StrEnum):
    """When the fact holds relative to the encounter."""

    CURRENT = "current"
    HISTORICAL = "historical"
    APPROXIMATE = "approximate"


class ReporterRole(StrEnum):
    """Who supplied the fact. An attendant-reported history is weaker evidence
    than a self-reported one and the physician must be able to see which."""

    SELF = "self"
    PARENT_GUARDIAN = "parent_guardian"
    FAMILY_ATTENDANT = "family_attendant"
    CAREGIVER = "caregiver"
    STAFF = "staff"


class Certainty(StrEnum):
    """How firmly the reporter committed to the value.

    `"maybe two weeks"` is APPROXIMATE and must stay APPROXIMATE. Nothing in the
    pipeline is permitted to promote certainty.
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
    """Sections of the intake, in the clinical order a history is taken."""

    IDENTITY = "identity"
    CONSENT = "consent"
    CHIEF_COMPLAINT = "chief_complaint"
    HPI = "hpi"
    RED_FLAG_SCREEN = "red_flag_screen"
    PAST_MEDICAL = "past_medical"
    PAST_SURGICAL = "past_surgical"
    MEDICATIONS = "medications"
    ALLERGIES = "allergies"
    FAMILY_HISTORY = "family_history"
    PERSONAL_HISTORY = "personal_history"
    REVIEW_OF_SYSTEMS = "review_of_systems"
    AYURVEDA = "ayurveda"
    DOCUMENTS = "documents"
    CONFIRMATION = "confirmation"


#: Canonical section order used by the state machine and the summary builder.
SECTION_ORDER: tuple[Section, ...] = (
    Section.IDENTITY,
    Section.CONSENT,
    Section.CHIEF_COMPLAINT,
    Section.HPI,
    Section.RED_FLAG_SCREEN,
    Section.PAST_MEDICAL,
    Section.PAST_SURGICAL,
    Section.MEDICATIONS,
    Section.ALLERGIES,
    Section.FAMILY_HISTORY,
    Section.PERSONAL_HISTORY,
    Section.REVIEW_OF_SYSTEMS,
    Section.AYURVEDA,
    Section.DOCUMENTS,
    Section.CONFIRMATION,
)


class AnswerShape(StrEnum):
    """Shape of answer a step expects. Drives both touch UI and voice parsing."""

    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    QUANTITY = "quantity"
    DURATION = "duration"
    SCALE = "scale"
    FREE_TEXT = "free_text"
    YES_NO_UNKNOWN = "yes_no_unknown"
    DATE = "date"
    CONFIRMATION = "confirmation"


class Severity(StrEnum):
    """Red-flag severity. Ordering matters for alert presentation."""

    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"


_SEVERITY_ORDER: tuple[Severity, ...] = (Severity.MODERATE, Severity.HIGH, Severity.CRITICAL)


def severity_rank(severity: Severity) -> int:
    """Position of `severity` on the low->high scale."""
    return _SEVERITY_ORDER.index(severity)


class IntakeState(StrEnum):
    """MediKiosk-owned lifecycle of a history-taking session.

    Orthogonal to `QueueState`. Neither derives from the other.
    """

    NOT_STARTED = "not_started"
    IDENTIFIED = "identified"
    CONSENTED = "consented"
    IN_PROGRESS = "in_progress"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    READY = "ready"
    SYNCED = "synced"
    PARTIAL = "partial"
    ABANDONED = "abandoned"
