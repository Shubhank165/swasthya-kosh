"""The physician report as a structure.

The rendered text is derived from this, never stored beside it. A structure the
dashboard can walk is what makes every line clickable back to its evidence:
`ReportLine.fact_ids` and `ReportLine.sources` are the link targets.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.clinical.enums import Section
from app.domain.record import Contradiction, RedFlagEvent, SourceRef
from app.domain.timeline.model import TimelineSnapshot


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
    #: The two halves of `text`, for a reader that can lay them out.
    #:
    #: `text` is `"{label}: {value}"` and stays that way — the plain-text
    #: renderer and the golden files are built on it. But a screen that has only
    #: that string can do nothing with it except print it, and a page of
    #: `label: value` in one weight is a pretty-printed dictionary, which is
    #: what a physician said the dashboard looked like. Splitting on `": "` in
    #: the client would be the dashboard deriving structure the builder already
    #: has, which §12 forbids, so the builder states it.
    #:
    #: `value` excludes the parenthesised "patient said …" that `text` carries,
    #: because `original_text` below already holds those words and a screen that
    #: renders both prints them twice. Both are `None` on a line that has no
    #: such halves — an unresolved line is a sentence, not a pair.
    label: str | None = None
    value: str | None = None
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


class TimelineEntry(BaseModel):
    """Where one uploaded document sits in time relative to this intake.

    A prescription or a certificate describes the patient on the day it was
    written, which may be weeks before they answered today's questions. Reading
    a value off it as though it were current — a diagnosis that has since
    resolved, a medicine since stopped — is a mistake the report has to make
    visible rather than leave to the reader to remember. `dated` is `False` when
    no date could be read: that is stated as its own problem, because an undated
    document cannot be placed on the timeline at all.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    #: The date printed on the document, ISO. `None` when none was legible.
    document_date: date | None = None
    #: Whole days between `document_date` and the intake. `None` when undated, or
    #: negative when the document is dated after the intake (a clock or a
    #: transcription problem worth surfacing).
    days_before_intake: int | None = None
    #: `False` -> the document carried no legible date. This is the problem the
    #: line reports.
    dated: bool = False
    #: The rendered sentence, in the report's language.
    text: str
    #: The document-channel facts this document produced, for click-through.
    fact_ids: tuple[str, ...] = ()


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
    #: One line per uploaded document placing it in time relative to this
    #: intake, or naming the absence of a date. Drives the DOCUMENT TIMELINE
    #: section.
    document_timeline: tuple[TimelineEntry, ...] = ()
    document_notes: tuple[ReportLine, ...] = ()
    #: The medical history timeline — the spec's dated-history
    #: requirement. `None` means it has not been built for this intake yet, and
    #: the renderer says so rather than printing an empty section: "not ready"
    #: and "nothing on record" look identical and mean opposite things.
    history: TimelineSnapshot | None = None
    #: Display label for every field id this report mentions.
    #:
    #: Conflicts and timeline entries carry field ids and no labels, and a
    #: reader with only an id can do nothing better than de-underscore it — so
    #: the dashboard was printing `chief_complaint` as a clinical heading, and
    #: the Hindi report was printing English ids. Resolving a label is the
    #: builder's job; it is the only place that holds the label table and the
    #: language at once.
    field_labels: dict[str, str] = Field(default_factory=dict)
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
