"""Where every clinical value came from.

A doctor reading "Metformin 500 mg" on the kiosk's sheet has to know whether the patient said it,
a prescription photo was read at 0.87 confidence, or a previous visit recorded it. Those three
carry very different weight, and a sheet that flattens them into one list invites a clinician to
trust an OCR guess as much as a spoken answer.

So no value reaches the report bare. `Sourced` wraps it with a source, an optional confidence, and
- once a clinician corrects it - a link back to what it replaced. Nothing is overwritten and
nothing is deleted: a correction is a new record pointing at the old one, so the original
extraction survives for audit even after the doctor has fixed it.

This module deliberately holds no clinical logic. It records origin; it never decides anything.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Source(str, Enum):
    """Ordered loosely by how much a clinician should trust it, most first."""

    DOCTOR_VERIFIED = "DOCTOR_VERIFIED"
    HOSPITAL_RECORD = "HOSPITAL_RECORD"
    ABHA = "ABHA"
    PATIENT_REPORTED = "PATIENT_REPORTED"
    REPRESENTATIVE_REPORTED = "REPRESENTATIVE_REPORTED"
    QUESTIONNAIRE = "QUESTIONNAIRE"
    OCR = "OCR"
    SYSTEM_INFERENCE = "SYSTEM_INFERENCE"


# Sources whose values a model or a camera produced rather than a person stating them. The report
# marks these so a clinician can see at a glance which lines deserve a second look.
MACHINE_DERIVED = frozenset({Source.OCR, Source.SYSTEM_INFERENCE})


class Sourced(BaseModel):
    """One clinical value plus where it came from."""

    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any
    source: Source
    # Only meaningful for machine-derived values. A patient saying "I have chest pain" has no
    # confidence score, and inventing one would imply a precision that does not exist.
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    # Free text a clinician can read: the transcript fragment, the OCR line, the visit date.
    evidence: str | None = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Set on the value being replaced, never on the replacement, so the chain reads forwards.
    superseded_by: str | None = None
    corrected_by: str | None = None

    @property
    def machine_derived(self) -> bool:
        return self.source in MACHINE_DERIVED

    def needs_review(self, threshold: float = 0.85) -> bool:
        """Machine-derived and either unscored or below the confidence a clinician should accept."""

        if not self.machine_derived:
            return False
        return self.confidence is None or self.confidence < threshold


class Ledger(BaseModel):
    """Every sourced value in one encounter, in the order it was learned.

    A list rather than a dict on purpose: the same key legitimately arrives more than once from
    different places, and the disagreement is itself clinical information. "Allergy: penicillin"
    from an ABHA record and "no known allergies" from the patient is exactly the conflict a doctor
    needs to see, not something the kiosk should quietly resolve.
    """

    model_config = ConfigDict(extra="forbid")

    entries: list[Sourced] = Field(default_factory=list)

    def record(
        self,
        key: str,
        value: Any,
        source: Source,
        confidence: float | None = None,
        evidence: str | None = None,
    ) -> Sourced:
        entry = Sourced(
            key=key, value=value, source=source, confidence=confidence, evidence=evidence
        )
        self.entries.append(entry)
        return entry

    def current(self, key: str) -> Sourced | None:
        """The value a clinician should act on: most trusted source, superseded ones excluded."""

        live = [e for e in self.entries if e.key == key and e.superseded_by is None]
        if not live:
            return None
        order = list(Source)
        return min(live, key=lambda e: order.index(e.source))

    def conflicts(self, key: str) -> list[Sourced]:
        """Live entries for a key that disagree. Surfaced to the doctor rather than resolved."""

        live = [e for e in self.entries if e.key == key and e.superseded_by is None]
        distinct = {str(e.value) for e in live}
        return live if len(distinct) > 1 else []

    def correct(self, key: str, value: Any, by: str, evidence: str | None = None) -> Sourced:
        """A clinician's fix. Supersedes rather than overwrites, so the original stays auditable."""

        replacement = Sourced(
            key=key,
            value=value,
            source=Source.DOCTOR_VERIFIED,
            evidence=evidence,
            corrected_by=by,
        )
        for entry in self.entries:
            if entry.key == key and entry.superseded_by is None:
                entry.superseded_by = by
        self.entries.append(replacement)
        return replacement

    def review_queue(self, threshold: float = 0.85) -> list[Sourced]:
        """Live values a clinician should check before relying on them."""

        return [
            entry
            for entry in self.entries
            if entry.superseded_by is None and entry.needs_review(threshold)
        ]

    def summary(self) -> dict[str, Any]:
        """Counts by source, for the header of the doctor's sheet."""

        counts: dict[str, int] = {}
        for entry in self.entries:
            if entry.superseded_by is None:
                counts[entry.source.value] = counts.get(entry.source.value, 0) + 1
        return {
            "by_source": counts,
            "needs_review": len(self.review_queue()),
            "corrected": sum(1 for e in self.entries if e.source is Source.DOCTOR_VERIFIED),
        }
