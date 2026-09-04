"""What an OCR pass read off a document.

Every item carries `confidence`, `page`, `bbox` and `raw_text` — §6.3 — because
the physician has to be able to click a dose on the report and land on the pixels
it was read from. An extraction with no bounding box is an assertion; one with a
bounding box is evidence.

`needs_verification` is the load-bearing flag. The OCR benchmark read `९००.२`
for `१००.२`: a single wrong digit, in a dose, is the most dangerous error this
system can make. Any numeric value below the configured floor is marked here and
rendered distinctly, with the raw text alongside.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.record import BoundingBox, DocumentKind


class ItemKind(StrEnum):
    """What sort of line this is. Drives which report section it lands in."""

    MEDICINE = "medicine"
    DIAGNOSIS = "diagnosis"
    LAB_RESULT = "lab_result"
    PROCEDURE = "procedure"
    #: Read, understood as text, but not classified. Kept, never dropped.
    OTHER = "other"


class RangeStatus(StrEnum):
    """Where a lab value sits against the range printed on that same report.

    `RANGE_UNAVAILABLE` is a first-class answer, not a failure. Reference ranges
    vary by lab, method, age and sex; a document that printed no range gets no
    flag, because flagging it against a range from somewhere else would be
    inventing a finding.
    """

    IN_RANGE = "in_range"
    BELOW_RANGE = "below_range"
    ABOVE_RANGE = "above_range"
    RANGE_UNAVAILABLE = "range_unavailable"
    #: The value itself was read too poorly to compare.
    NOT_COMPARABLE = "not_comparable"


class ReferenceRange(BaseModel):
    """A range **as printed on this document**. Never a hardcoded default."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    low: float | None = None
    high: float | None = None
    unit: str | None = None
    #: Exactly as it appeared, e.g. `"12.0 - 15.0 g/dL"`.
    raw_text: str | None = None

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if self.low is None and self.high is None:
            raise ValueError("a reference range needs at least one bound")
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError("reference range low bound exceeds its high bound")
        return self

    def render(self) -> str:
        if self.raw_text:
            return self.raw_text
        unit = f" {self.unit}" if self.unit else ""
        if self.low is not None and self.high is not None:
            return f"{self.low}–{self.high}{unit}"
        if self.low is not None:
            return f"≥ {self.low}{unit}"
        return f"≤ {self.high}{unit}"


class Medicine(BaseModel):
    """A prescribed medicine as printed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    dose_magnitude: float | None = None
    dose_unit: str | None = None
    frequency: str | None = None
    duration: str | None = None
    route: str | None = None
    #: A normalised key for interaction lookup. `None` when the name did not
    #: resolve — an unrecognised medicine is never guessed at.
    ingredient_key: str | None = None

    def render(self) -> str:
        parts = [self.name]
        if self.dose_magnitude is not None:
            unit = f" {self.dose_unit}" if self.dose_unit else ""
            magnitude = (
                int(self.dose_magnitude)
                if float(self.dose_magnitude).is_integer()
                else self.dose_magnitude
            )
            parts.append(f"{magnitude}{unit}")
        if self.frequency:
            parts.append(self.frequency)
        if self.duration:
            parts.append(f"for {self.duration}")
        if self.route:
            parts.append(f"({self.route})")
        return " ".join(parts)


class LabResult(BaseModel):
    """One lab analyte, its value, and the range printed beside it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    analyte: str = Field(min_length=1)
    value: float | None = None
    unit: str | None = None
    reference_range: ReferenceRange | None = None
    #: A result reported as text (`"Positive"`, `"Not detected"`).
    text_value: str | None = None

    def render(self) -> str:
        if self.value is None:
            return f"{self.analyte}: {self.text_value or 'not read'}"
        magnitude = int(self.value) if float(self.value).is_integer() else self.value
        unit = f" {self.unit}" if self.unit else ""
        rendered = f"{self.analyte}: {magnitude}{unit}"
        if self.reference_range is not None:
            rendered += f" (ref {self.reference_range.render()})"
        return rendered


class DocumentItem(BaseModel):
    """One extracted line, with the evidence that produced it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    kind: ItemKind
    #: What the OCR pass actually read, after redaction. Never the pre-redaction
    #: text — that exists only in the image.
    raw_text: str
    page: int = Field(ge=1)
    bbox: BoundingBox | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    #: Set when a numeric value fell below the confidence floor. Rendered
    #: distinctly, with the raw text beside it.
    needs_verification: bool = False
    medicine: Medicine | None = None
    lab_result: LabResult | None = None
    #: For diagnoses and procedures.
    label: str | None = None
    range_status: RangeStatus = RangeStatus.RANGE_UNAVAILABLE

    @model_validator(mode="after")
    def _payload_matches_kind(self) -> Self:
        if self.kind is ItemKind.MEDICINE and self.medicine is None:
            raise ValueError("a medicine item must carry its medicine")
        if self.kind is ItemKind.LAB_RESULT and self.lab_result is None:
            raise ValueError("a lab_result item must carry its result")
        if self.kind in {ItemKind.DIAGNOSIS, ItemKind.PROCEDURE} and not self.label:
            raise ValueError(f"a {self.kind} item must carry a label")
        return self

    def render(self) -> str:
        if self.medicine is not None:
            return self.medicine.render()
        if self.lab_result is not None:
            return self.lab_result.render()
        return self.label or self.raw_text


class QualityVerdict(StrEnum):
    """The quality gate's decision, before any reading is attempted."""

    ACCEPTED = "accepted"
    #: Too blurry, too dark, too skewed. The patient is asked to reshoot rather
    #: than being handed a confident misreading.
    REJECTED = "rejected"


class DocumentExtraction(BaseModel):
    """The full result of reading one document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    kind: DocumentKind = DocumentKind.OTHER
    page_count: int = Field(default=1, ge=1)
    items: list[DocumentItem] = Field(default_factory=list)
    #: Per-page redacted plain text, for the evidence panel. Never logged.
    page_text: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    quality: QualityVerdict = QualityVerdict.ACCEPTED
    quality_reason: str | None = None
    #: The date printed on the document, when one was found.
    document_date: date | None = None
    issuing_facility: str | None = None
    #: Identifier kinds the redaction pass masked, and how many of each.
    redactions: dict[str, int] = Field(default_factory=dict)
    #: Which provider and model produced this. `"mock"` in tests and demo mode.
    provider: str = "mock"
    model_id: str | None = None
    #: True when the result was served from the demo fixture cache.
    demo: bool = False

    @property
    def low_confidence(self) -> bool:
        return any(item.needs_verification for item in self.items)

    @property
    def was_rejected(self) -> bool:
        return self.quality is QualityVerdict.REJECTED

    def medicines(self) -> tuple[DocumentItem, ...]:
        return tuple(i for i in self.items if i.kind is ItemKind.MEDICINE)

    def lab_results(self) -> tuple[DocumentItem, ...]:
        return tuple(i for i in self.items if i.kind is ItemKind.LAB_RESULT)

    def diagnoses(self) -> tuple[DocumentItem, ...]:
        return tuple(i for i in self.items if i.kind is ItemKind.DIAGNOSIS)
