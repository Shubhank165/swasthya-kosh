"""The canonical record.

Everything downstream reads this and only this. The report builder, the FHIR
mapper, the storage layer and the dashboard API never see a kiosk payload — they
see a `CanonicalRecord`. That is what makes a new input shape a contained edit
(§4.2): two new files and one registry line, with nothing below this module
aware that anything changed.

Three invariants are structural here rather than conventional, because each one
has already been got wrong by a system somewhere:

1. **Five statuses, never a boolean.** `unresolved` is not `not_asked` and
   neither is `no`. `FieldStatus` has exactly five members and no code path
   collapses them; `Fact.denies()` is the only way to ask "did the patient say
   no", and it requires an explicit `answered` status carrying a false value.
2. **Certainty never rises.** `"maybe two weeks"` stays approximate. `revise`
   refuses a promotion; only `verified_by_physician` — a human act, recorded
   with the actor — may raise it.
3. **The original text travels with the value.** `original_text` is populated
   from whatever the patient actually said and is never dropped, so the report
   can print the normalised term and the patient's own words side by side.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.clinical.enums import Certainty, ReporterRole, Section, certainty_rank

RECORD_VERSION = "1.0"


class FieldStatus(StrEnum):
    """Whether a field was settled, and if not, why not.

    This vocabulary arrives from the kiosk and must survive normalisation,
    storage and rendering unchanged. Any code path that maps two of these onto
    one value is a defect — `tests/safety/test_status_vocabulary.py` proves the
    five stay distinct all the way to the rendered report.
    """

    #: The question was put and an answer was bound.
    ANSWERED = "answered"
    #: The Jetson asked twice and could not bind an answer. Not `not_asked`, and
    #: emphatically not `no`.
    UNRESOLVED = "unresolved"
    #: The interview never reached this field.
    NOT_ASKED = "not_asked"
    #: The field cannot apply to this patient (pregnancy in a male patient).
    NOT_APPLICABLE = "not_applicable"
    #: The patient was asked and declined to answer.
    REFUSED = "refused"


#: Statuses that carry no value and must not be given one.
VALUELESS_STATUSES: frozenset[FieldStatus] = frozenset(
    {
        FieldStatus.UNRESOLVED,
        FieldStatus.NOT_ASKED,
        FieldStatus.NOT_APPLICABLE,
        FieldStatus.REFUSED,
    }
)


class IntakeStatus(StrEnum):
    """How the intake ended on the device."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    #: The Jetson stopped the interview because a red-flag criterion fired.
    ABORTED_RED_FLAG = "aborted_red_flag"
    ABANDONED = "abandoned"


class FactChannel(StrEnum):
    """Which pipeline produced the fact.

    The contradiction detector uses this: the voice channel is what the patient
    says today, the document and prior-record channels are what we already held.
    """

    VOICE = "voice"
    TOUCH = "touch"
    DOCUMENT = "document"
    PRIOR_RECORD = "prior_record"
    STAFF = "staff"


#: Channels representing what we already held about this patient.
RECORD_CHANNELS: frozenset[FactChannel] = frozenset(
    {FactChannel.DOCUMENT, FactChannel.PRIOR_RECORD}
)
#: Channels representing the patient speaking during this intake.
TODAY_CHANNELS: frozenset[FactChannel] = frozenset(
    {FactChannel.VOICE, FactChannel.TOUCH, FactChannel.STAFF}
)


class PatientRefType(StrEnum):
    """How a patient is identified. ABHA is never mandatory."""

    ABHA = "abha"
    HOSPITAL_ID = "hospital_id"
    #: A matching aid only. The whole number is never stored.
    AADHAAR_LAST4 = "aadhaar_last4"
    GUEST = "guest"


# --- typed values ------------------------------------------------------------
#
# Discriminated on `kind` so the union round-trips through JSON storage and the
# API without a custom encoder. `render` is the single place a value becomes
# text, which is what makes the report deterministic.


class _Value(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    def render(self) -> str:  # pragma: no cover - overridden by every member
        raise NotImplementedError


class Quantity(_Value):
    """A magnitude with a unit. The unit is mandatory: a bare `120` is not
    clinical data."""

    kind: Literal["quantity"] = "quantity"
    magnitude: float
    unit: str = Field(min_length=1)

    def render(self) -> str:
        return f"{_trim(self.magnitude)} {self.unit}"


class Duration(_Value):
    """A span in the unit the patient used.

    Deliberately not normalised to seconds: "about 2 weeks" and "14 days" carry
    different precision and the physician should see which was said.
    """

    kind: Literal["duration"] = "duration"
    magnitude: float = Field(ge=0)
    unit: Literal["hour", "day", "week", "month", "year"]

    def render(self) -> str:
        magnitude = _trim(self.magnitude)
        plural = "" if magnitude == "1" else "s"
        return f"{magnitude} {self.unit}{plural}"


class Coded(_Value):
    """A value drawn from a controlled vocabulary."""

    kind: Literal["coded"] = "coded"
    code: str = Field(min_length=1)
    system: str | None = None
    display: str | None = None

    def render(self) -> str:
        return self.display or self.code.replace("_", " ")


class Text(_Value):
    """Free narrative, already normalised. The verbatim original lives on
    `Fact.original_text`."""

    kind: Literal["text"] = "text"
    text: str

    def render(self) -> str:
        return self.text


class Boolean(_Value):
    """A genuinely binary attribute — `currently_taking`, `breathlessness`.

    Never a stand-in for `FieldStatus`. A `Boolean(value=False)` on an
    `answered` field means the patient said no; a missing field means nothing of
    the sort, and there is no way to write one as the other.
    """

    kind: Literal["boolean"] = "boolean"
    value: bool

    def render(self) -> str:
        return "yes" if self.value else "no"


class DateValue(_Value):
    """A calendar date, with precision so "sometime in 2019" survives."""

    kind: Literal["date"] = "date"
    value: date
    precision: Literal["day", "month", "year"] = "day"

    def render(self) -> str:
        if self.precision == "year":
            return str(self.value.year)
        if self.precision == "month":
            return self.value.strftime("%B %Y")
        return self.value.isoformat()


class Scale(_Value):
    """A point on a bounded ordinal scale, e.g. pain 0-10."""

    kind: Literal["scale"] = "scale"
    value: float
    minimum: float = 0.0
    maximum: float = 10.0

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if self.minimum >= self.maximum:
            raise ValueError("scale minimum must be below maximum")
        if not self.minimum <= self.value <= self.maximum:
            raise ValueError(f"scale value {self.value} outside {self.minimum}..{self.maximum}")
        return self

    def render(self) -> str:
        return f"{_trim(self.value)}/{_trim(self.maximum)}"


FactValue = Annotated[
    Quantity | Duration | Coded | Text | Boolean | DateValue | Scale,
    Field(discriminator="kind"),
]


def _trim(value: float) -> str:
    """`3.0` renders as `3`; `3.5` renders as `3.5`."""
    return str(int(value)) if float(value).is_integer() else str(value)


def render_value(value: FactValue | None) -> str | None:
    return None if value is None else value.render()


# --- provenance --------------------------------------------------------------


class BoundingBox(BaseModel):
    """Normalised 0..1 rectangle on a document page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)


class TurnSource(BaseModel):
    """The interview turn a fact came from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["turn"] = "turn"
    turn_id: int
    question_id: str | None = None
    #: The words that produced the binding. Clinical text — never logged.
    transcript_excerpt: str | None = None

    def label(self) -> str:
        return f"turn {self.turn_id}"


class DocumentSource(BaseModel):
    """The document region a fact was read from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["document"] = "document"
    document_id: str
    page: int = Field(ge=1)
    bbox: BoundingBox | None = None

    def label(self) -> str:
        return f"{self.document_id} p{self.page}"


class EntrySource(BaseModel):
    """Entered by a person — staff, or carried forward from a prior record.

    The evidence here is the act of entry, so the actor is what is recorded.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["entry"] = "entry"
    entered_by: str
    prior_intake_id: str | None = None

    def label(self) -> str:
        return f"entered by {self.entered_by}"


SourceRef = Annotated[TurnSource | DocumentSource | EntrySource, Field(discriminator="kind")]


class PatientRef(BaseModel):
    """How this intake identifies its patient.

    A guest intake is complete and valid on its own; registration links it to a
    patient later.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: PatientRefType = PatientRefType.GUEST
    value: str | None = None

    @model_validator(mode="after")
    def _check_value(self) -> Self:
        if self.type is PatientRefType.GUEST:
            return self
        if not self.value:
            raise ValueError(f"a '{self.type}' patient reference requires a value")
        if self.type is PatientRefType.AADHAAR_LAST4 and (
            len(self.value) != 4 or not self.value.isdigit()
        ):
            raise ValueError(
                "aadhaar_last4 must be exactly four digits — the whole number is "
                "never accepted and never stored"
            )
        return self

    def key(self) -> str:
        """Stable lookup key for history retrieval."""
        return self.type.value if self.value is None else f"{self.type.value}:{self.value}"


class IngestProvenance(BaseModel):
    """Which versions of which things produced this record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    engine_version: str | None = None
    content_version: str | None = None
    kiosk_id: str | None = None
    #: True when the payload failed its contract and was restructured by the
    #: repair model. Every fact it produced carries `repaired = True` too.
    repaired: bool = False
    #: True when even repair failed. The raw payload is stored; a human looks.
    needs_manual_review: bool = False


# --- the fact ----------------------------------------------------------------


class CertaintyIncreaseError(ValueError):
    """A revision claimed more confidence than its predecessor.

    Guards invariant 2. `"maybe two weeks"` must never quietly become
    `"2 weeks"`; only physician verification may raise certainty, and that path
    records who did it.
    """


class Fact(BaseModel):
    """One observation about one field, with everything needed to defend it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str
    #: The kiosk's field name — `chief_complaint`, `severity`, `duration`. Maps
    #: to a concept in the ontology when one exists; kept verbatim when it does
    #: not, so an unmapped field is never lost.
    field_id: str = Field(min_length=1)
    status: FieldStatus
    value: FactValue | None = None
    #: What the patient actually said, verbatim, in their own script.
    original_text: str | None = None
    language: str | None = None
    source: SourceRef
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reported_by: ReporterRole = ReporterRole.SELF
    certainty: Certainty = Certainty.REPORTED
    section: Section = Section.HPI
    channel: FactChannel = FactChannel.VOICE
    physician_verified: bool = False
    #: Produced by the repair model rather than the extractor. Renders as
    #: lower-confidence and can never be `physician_verified` at ingest.
    repaired: bool = False
    #: A numeric OCR value below the confidence floor. Rendered distinctly with
    #: the raw text alongside.
    needs_verification: bool = False
    recorded_at: datetime
    supersedes: str | None = None
    #: Why this fact exists — a rule id, an extractor note, a verifier. Never
    #: clinical text; safe to log.
    note: str | None = None

    @field_validator("original_text", "note")
    @classmethod
    def _no_empty_strings(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        if self.status in VALUELESS_STATUSES and self.value is not None:
            raise ValueError(
                f"a '{self.status}' fact must not carry a value: "
                "unresolved, refused, not_asked and not_applicable mean no answer was bound"
            )
        if self.repaired and self.physician_verified:
            raise ValueError(
                "a repaired fact may not be physician-verified at ingest; "
                "verification is a human act performed after the fact exists"
            )
        return self

    # --- queries ------------------------------------------------------------

    @property
    def is_answered(self) -> bool:
        """True only when the question was put and an answer was bound."""
        return self.status is FieldStatus.ANSWERED

    @property
    def is_established(self) -> bool:
        """True when the record says something positive about this field."""
        return self.status is FieldStatus.ANSWERED and self.value is not None

    def denies(self) -> bool:
        """True only for an explicit, answered `no`.

        The one legitimate way to ask "did the patient deny this". A missing
        field, an unresolved field and a refused field all answer `False` here
        and none of them may ever be rendered as a denial.
        """
        return self.status is FieldStatus.ANSWERED and isinstance(self.value, Boolean) and (
            self.value.value is False
        )

    def asserts(self) -> bool:
        """True for an explicit, answered `yes` on a boolean field."""
        return self.status is FieldStatus.ANSWERED and isinstance(self.value, Boolean) and (
            self.value.value is True
        )

    def rendered_value(self) -> str | None:
        return render_value(self.value)

    def source_label(self) -> str:
        return self.source.label()

    @property
    def is_from_record(self) -> bool:
        return self.channel in RECORD_CHANNELS

    @property
    def is_from_today(self) -> bool:
        return self.channel in TODAY_CHANNELS

    # --- revision -----------------------------------------------------------

    def revise(
        self,
        *,
        new_fact_id: str,
        recorded_at: datetime,
        allow_certainty_increase: bool = False,
        **changes: object,
    ) -> Fact:
        """The successor revision of this fact.

        Certainty may not increase unless `allow_certainty_increase` is set,
        which only `verified_by_physician` does. A revision is a fresh claim:
        prior sign-off does not carry over.
        """
        next_certainty = changes.get("certainty", self.certainty)
        assert isinstance(next_certainty, Certainty)
        if not allow_certainty_increase and certainty_rank(next_certainty) > certainty_rank(
            self.certainty
        ):
            raise CertaintyIncreaseError(
                f"cannot promote certainty {self.certainty} -> {next_certainty} "
                f"for field '{self.field_id}' without human confirmation"
            )
        next_status = changes.get("status", self.status)
        if next_status in VALUELESS_STATUSES:
            changes["value"] = None
        return self.model_copy(
            update={
                **changes,
                "fact_id": new_fact_id,
                "recorded_at": recorded_at,
                "supersedes": self.fact_id,
                "physician_verified": False,
            }
        )

    def verified_by_physician(
        self, *, new_fact_id: str, recorded_at: datetime, physician_id: str
    ) -> Fact:
        """A physician signed this fact off. Records who, in `note`.

        This is the only path that may raise certainty, and it does so only to
        `CONFIRMED` — a physician confirming what was said, not inventing a value
        where none was bound. An unresolved field stays unresolved: there is
        nothing to confirm.
        """
        certainty = (
            Certainty.CONFIRMED if self.status is FieldStatus.ANSWERED else self.certainty
        )
        return self.model_copy(
            update={
                "fact_id": new_fact_id,
                "certainty": certainty,
                "physician_verified": True,
                "recorded_at": recorded_at,
                "supersedes": self.fact_id,
                "note": f"verified_by={physician_id}",
            }
        )


# --- everything attached to an intake ----------------------------------------


class RedFlagEvent(BaseModel):
    """A criterion the Jetson fired during the interview.

    An already-fired event, not something to re-evaluate. The backend persists
    it, surfaces it and waits for a human to acknowledge it. It runs no rules.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str = Field(min_length=1)
    fired_at_turn: int | None = None
    criteria_met: tuple[str, ...] = ()
    severity: str = "high"
    label: str | None = None
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None

    @property
    def is_acknowledged(self) -> bool:
        return self.acknowledged_by is not None


class DocumentKind(StrEnum):
    PRESCRIPTION = "prescription"
    LAB_REPORT = "lab_report"
    DISCHARGE_SUMMARY = "discharge_summary"
    OTHER = "other"


class DocumentStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    #: The quality gate turned it away. The patient is asked to reshoot.
    REJECTED_QUALITY = "rejected_quality"
    FAILED = "failed"


class DocumentRef(BaseModel):
    """A document attached to the intake, and how far processing got."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    kind: DocumentKind = DocumentKind.OTHER
    status: DocumentStatus = DocumentStatus.RECEIVED
    page_count: int = 1
    #: Overall OCR confidence. Surfaced, not hidden: the physician is told when
    #: the machine was unsure.
    confidence: float | None = None
    low_confidence: bool = False
    #: Present when the quality gate rejected the image.
    rejection_reason: str | None = None
    uploaded_at: datetime | None = None
    processed_at: datetime | None = None

    @property
    def is_processed(self) -> bool:
        return self.status is DocumentStatus.PROCESSED


class ConflictKind(StrEnum):
    """What sort of disagreement this is. Drives how the report words it."""

    STATUS = "status"
    VALUE = "value"
    PRESENCE_ONLY_IN_RECORD = "presence_only_in_record"


class ConflictSide(BaseModel):
    """One half of a conflict, with everything needed to display its provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str
    statement: str
    channel: FactChannel
    source_label: str
    confidence: float | None = None
    original_text: str | None = None


class Contradiction(BaseModel):
    """A disagreement between two facts about the same field. Never resolved.

    Deciding which of two conflicting histories is true is a clinical act, and
    the whole value of surfacing the conflict is destroyed if software silently
    picks a winner.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    field_id: str
    kind: ConflictKind
    reported_today: ConflictSide | None = None
    from_record: ConflictSide
    resolution: str = "Physician verification required"

    def fact_ids(self) -> tuple[str, ...]:
        ids = [self.from_record.fact_id]
        if self.reported_today is not None:
            ids.insert(0, self.reported_today.fact_id)
        return tuple(ids)


def live(facts: Sequence[Fact]) -> tuple[Fact, ...]:
    """One fact per field per channel: superseded revisions removed.

    Both channels survive, because a conflict needs both halves. Collapsing to
    one fact per field here is what would make a scan silently overwrite what
    the patient said.

    Module-level rather than a method, because the worklist reads facts straight
    out of the repository for many intakes at once and must collapse them the
    same way a loaded record does. Two implementations of "which revision counts"
    is one more than the number that can stay correct.
    """
    superseded = {f.supersedes for f in facts if f.supersedes is not None}
    return tuple(f for f in facts if f.fact_id not in superseded)


class CanonicalRecord(BaseModel):
    """What everything downstream reads.

    Versioned separately from the input contracts and changed rarely — and when
    it changes, additively: a new optional field, never a rename. A rename here
    breaks the report, the FHIR bundle, the dashboard and every stored row at
    once.
    """

    model_config = ConfigDict(extra="forbid")

    record_version: str = RECORD_VERSION
    intake_id: UUID
    hospital_id: str = Field(min_length=1)
    patient_ref: PatientRef = PatientRef()
    language: str = "en"
    status: IntakeStatus
    reported_by: ReporterRole = ReporterRole.SELF
    department_code: str | None = None
    facts: list[Fact] = Field(default_factory=list)
    red_flags: list[RedFlagEvent] = Field(default_factory=list)
    documents: list[DocumentRef] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    provenance: IngestProvenance
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    # --- queries ------------------------------------------------------------

    def live_facts(self) -> tuple[Fact, ...]:
        """One fact per field per channel: superseded revisions removed."""
        return live(self.facts)

    def voice_facts(self) -> tuple[Fact, ...]:
        return tuple(f for f in self.live_facts() if f.is_from_today)

    def record_facts(self) -> tuple[Fact, ...]:
        return tuple(f for f in self.live_facts() if f.is_from_record)

    def fact(self, fact_id: str) -> Fact | None:
        return next((f for f in self.facts if f.fact_id == fact_id), None)

    def facts_in(self, section: Section) -> tuple[Fact, ...]:
        return tuple(f for f in self.live_facts() if f.section is section)

    def by_field(self, field_id: str) -> tuple[Fact, ...]:
        return tuple(f for f in self.live_facts() if f.field_id == field_id)

    def unresolved_fields(self) -> tuple[str, ...]:
        """Fields the Jetson asked but could not bind. Ordered, deduplicated."""
        return tuple(
            sorted({f.field_id for f in self.live_facts() if f.status is FieldStatus.UNRESOLVED})
        )

    def unanswered_fields(self) -> tuple[str, ...]:
        """Everything that did not settle, for whatever reason.

        These appear on the report under *Unresolved*, worded as "not
        established". They are never omitted and never rendered as absent.
        """
        return tuple(
            sorted(
                {
                    f.field_id
                    for f in self.live_facts()
                    if f.status is not FieldStatus.ANSWERED
                    and f.status is not FieldStatus.NOT_APPLICABLE
                }
            )
        )

    @property
    def needs_review(self) -> bool:
        """True when a human must look before this record is trusted.

        Any of: repair ran, repair failed, a red flag is unacknowledged, a fact
        needs digit verification, or a contradiction is open.
        """
        return bool(
            self.provenance.repaired
            or self.provenance.needs_manual_review
            or self.contradictions
            or any(not e.is_acknowledged for e in self.red_flags)
            or any(f.needs_verification for f in self.live_facts())
        )

    @property
    def repaired_fact_count(self) -> int:
        return sum(1 for f in self.live_facts() if f.repaired)
