"""The physician report as a structure.

The rendered text is derived from this, never stored beside it. A structure the
dashboard can walk is what makes every line clickable back to its evidence:
`ReportLine.fact_ids` and `ReportLine.sources` are the link targets.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.clinical.enums import Section
from app.domain.record import Contradiction, RedFlagEvent, SourceRef


class LineMarker(BaseModel):
    """A qualifier printed against a line, and why.

    Markers are how a report says "this is weaker than the line next to it"
    without demoting it out of sight. Each one is rendered as a bracketed note
    and carries a machine-readable `code` so the dashboard can style it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    text: str


class ReportLine(BaseModel):
    """One rendered statement plus the evidence it rests on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    field_ids: tuple[str, ...] = ()
    fact_ids: tuple[str, ...] = ()
    sources: tuple[SourceRef, ...] = ()
    markers: tuple[LineMarker, ...] = ()
    #: The patient's own words, verbatim, in their own script. Never translated.
    original_text: str | None = None
    original_language: str | None = None

    def rendered(self) -> str:
        """The line as it appears in the plain-text report."""
        parts = [self.text]
        if self.markers:
            parts.append("[" + "; ".join(m.text for m in self.markers) + "]")
        return " ".join(parts)


class ReportSection(BaseModel):
    """A titled block of lines."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    section: Section
    title: str
    lines: tuple[ReportLine, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.lines


class InteractionLine(BaseModel):
    """One sourced interaction pair. A request to look, never a recommendation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    severity: str
    source: str


class PhysicianReport(BaseModel):
    """The finished document.

    Deterministic: the same canonical record renders byte-identical output every
    time. `tests/report/` holds the golden files that hold that true.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    intake_id: str
    hospital_id: str
    language: str
    #: Version of the *builder*, not of the record. Bumped when the rendering
    #: changes, so a golden-file diff is attributable.
    template_version: str = "1.0"
    sections: tuple[ReportSection, ...] = ()
    unresolved: tuple[ReportLine, ...] = ()
    conflicts: tuple[Contradiction, ...] = ()
    alerts: tuple[RedFlagEvent, ...] = ()
    interactions: tuple[InteractionLine, ...] = ()
    document_notes: tuple[ReportLine, ...] = ()
    #: True when any fact was produced by the repair model.
    contains_repaired: bool = False
    #: True when any value needs a human to check it against the original.
    needs_verification: bool = False
    demo: bool = False
    generated_at: datetime | None = None
    #: Set once a physician signs the report off.
    physician_verified_by: str | None = None

    def all_fact_ids(self) -> tuple[str, ...]:
        return tuple(
            fid for section in self.sections for line in section.lines for fid in line.fact_ids
        )

    def line_for_fact(self, fact_id: str) -> ReportLine | None:
        for section in self.sections:
            for line in section.lines:
                if fact_id in line.fact_ids:
                    return line
        return None


class ReportBundle(BaseModel):
    """A report plus the rendered text, for the API."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report: PhysicianReport
    text: str = Field(description="Plain-text rendering, in the report's language")
