"""Provenance primitives: identifiers, source references and typed fact values.

`SourceRef` is the reason a physician can click a line of the generated history
and land on the exact transcript offset or the exact region of the scanned
prescription it came from. Without that, the report is an assertion; with it,
it is evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import NewType

FactId = NewType("FactId", str)
IntakeId = NewType("IntakeId", str)
DocumentId = NewType("DocumentId", str)
SegmentId = NewType("SegmentId", str)
TicketId = NewType("TicketId", str)
QueueId = NewType("QueueId", str)
QueueInstanceId = NewType("QueueInstanceId", str)
AlertId = NewType("AlertId", str)
UserId = NewType("UserId", str)
PatientId = NewType("PatientId", str)


@dataclass(frozen=True, slots=True)
class ConceptRef:
    """A normalised clinical concept plus, optionally, the coded terminology it
    resolves to. `code` stays `None` when no mapping exists — we never invent one."""

    concept_id: str
    system: str | None = None
    code: str | None = None
    display: str | None = None

    def __post_init__(self) -> None:
        if not self.concept_id:
            raise ValueError("concept_id must not be empty")

    def __str__(self) -> str:
        return self.concept_id


@dataclass(frozen=True, slots=True)
class TranscriptRef:
    """Points at a span of a voice transcript."""

    segment_id: SegmentId
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms < 0:
            raise ValueError("transcript offsets must be non-negative")
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must not precede start_ms")


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Normalised 0..1 rectangle on a document page."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        for name, value in (
            ("x", self.x),
            ("y", self.y),
            ("width", self.width),
            ("height", self.height),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within 0.0..1.0, got {value}")


@dataclass(frozen=True, slots=True)
class DocumentRef:
    """Points at a region of an uploaded document."""

    document_id: DocumentId
    page: int
    bbox: BoundingBox | None = None

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page is 1-indexed")


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Evidence pointer. Exactly one of the three carriers is populated.

    `entered_by` covers touch, staff and prior-record entry, where the evidence
    is the act of entry itself and the actor is what matters.
    """

    transcript: TranscriptRef | None = None
    document: DocumentRef | None = None
    entered_by: str | None = None

    def __post_init__(self) -> None:
        carriers = [self.transcript, self.document, self.entered_by]
        if sum(1 for c in carriers if c is not None) != 1:
            raise ValueError("SourceRef must carry exactly one of transcript/document/entered_by")

    @classmethod
    def from_transcript(cls, segment_id: SegmentId, start_ms: int, end_ms: int) -> SourceRef:
        return cls(transcript=TranscriptRef(segment_id, start_ms, end_ms))

    @classmethod
    def from_document(
        cls, document_id: DocumentId, page: int, bbox: BoundingBox | None = None
    ) -> SourceRef:
        return cls(document=DocumentRef(document_id, page, bbox))

    @classmethod
    def from_actor(cls, actor: str) -> SourceRef:
        return cls(entered_by=actor)


# --- typed fact values -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Quantity:
    """A magnitude with a unit. Unit is mandatory: a bare `120` is not clinical data."""

    magnitude: float
    unit: str

    def __post_init__(self) -> None:
        if not self.unit:
            raise ValueError("Quantity requires a unit")

    def render(self) -> str:
        magnitude = int(self.magnitude) if self.magnitude.is_integer() else self.magnitude
        return f"{magnitude} {self.unit}"


@dataclass(frozen=True, slots=True)
class Duration:
    """A span expressed in the unit the patient used.

    Deliberately not normalised to seconds: "about 2 weeks" and "14 days" carry
    different precision and the physician should see which was said.
    """

    magnitude: float
    unit: str  # hours | days | weeks | months | years

    _UNITS = frozenset({"hours", "days", "weeks", "months", "years"})

    def __post_init__(self) -> None:
        if self.unit not in Duration._UNITS:
            raise ValueError(f"unsupported duration unit: {self.unit}")
        if self.magnitude < 0:
            raise ValueError("duration magnitude must be non-negative")

    def render(self) -> str:
        magnitude = int(self.magnitude) if self.magnitude.is_integer() else self.magnitude
        unit = self.unit[:-1] if magnitude == 1 else self.unit
        return f"{magnitude} {unit}"


@dataclass(frozen=True, slots=True)
class CodedValue:
    """A value drawn from a controlled vocabulary."""

    code: str
    system: str | None = None
    display: str | None = None

    def render(self) -> str:
        return self.display or self.code


@dataclass(frozen=True, slots=True)
class TextValue:
    """Free narrative. `text` is already the normalised rendering; the verbatim
    original lives on the fact's `original_expression`."""

    text: str

    def render(self) -> str:
        return self.text


@dataclass(frozen=True, slots=True)
class BooleanValue:
    """Used only for genuinely binary attributes of an otherwise-present fact
    (e.g. `currently_taking`). Never used to represent `FactStatus`."""

    value: bool

    def render(self) -> str:
        return "yes" if self.value else "no"


@dataclass(frozen=True, slots=True)
class DateValue:
    """A calendar date, with a precision marker so "sometime in 2019" survives."""

    value: date
    precision: str = "day"  # day | month | year

    _PRECISIONS = frozenset({"day", "month", "year"})

    def __post_init__(self) -> None:
        if self.precision not in DateValue._PRECISIONS:
            raise ValueError(f"unsupported date precision: {self.precision}")

    def render(self) -> str:
        if self.precision == "year":
            return str(self.value.year)
        if self.precision == "month":
            return self.value.strftime("%B %Y")
        return self.value.isoformat()


@dataclass(frozen=True, slots=True)
class ScaleValue:
    """A point on a bounded ordinal scale, e.g. pain 0-10."""

    value: float
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if self.minimum >= self.maximum:
            raise ValueError("scale minimum must be below maximum")
        if not self.minimum <= self.value <= self.maximum:
            raise ValueError(f"scale value {self.value} outside {self.minimum}..{self.maximum}")

    def render(self) -> str:
        value = int(self.value) if float(self.value).is_integer() else self.value
        maximum = int(self.maximum) if float(self.maximum).is_integer() else self.maximum
        return f"{value}/{maximum}"


FactValue = Quantity | Duration | CodedValue | TextValue | BooleanValue | DateValue | ScaleValue


def render_value(value: FactValue | None) -> str | None:
    """Human-readable rendering of a fact value, or None when there is none."""
    return None if value is None else value.render()
