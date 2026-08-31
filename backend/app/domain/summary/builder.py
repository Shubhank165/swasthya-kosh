"""Deterministic summary builder.

Assembles the physician-facing draft from the fact set. Every rendered line
carries the fact ids it was built from, so the UI can turn any statement into a
click through to the transcript offset or document region behind it.

Nothing is dropped. A concept that was asked and not established prints under
`Unresolved` rather than quietly vanishing, because a physician needs to know
the difference between "no allergies" and "we never got to allergies".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.domain.clinical.enums import FactStatus, Section
from app.domain.clinical.fact import ClinicalFact
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.clinical.provenance import FactId
from app.domain.contradictions.detector import Contradiction
from app.domain.coverage.coverage import CoverageReport
from app.domain.redflags.evaluator import RedFlagAlert
from app.domain.summary.templates import (
    CONFLICTS_TITLE,
    FOOTER_DISCLAIMER,
    HEADER_DISCLAIMER,
    NO_ALERTS_LINE,
    NO_CONFLICTS_LINE,
    NOTHING_RECORDED_LINE,
    REPORT_SECTIONS,
    SAFETY_TITLE,
    SECTION_TITLES,
    UNRESOLVED_TITLE,
    annotate,
    find_unsupported_assertions,
)


@dataclass(frozen=True, slots=True)
class SummaryLine:
    """One rendered statement plus the evidence it rests on."""

    text: str
    fact_ids: tuple[FactId, ...] = field(default_factory=tuple)
    #: Verbatim patient words, preserved beside the normalised rendering.
    original_expression: str | None = None
    original_language: str | None = None


@dataclass(frozen=True, slots=True)
class SummarySection:
    """A titled block of lines."""

    section: Section
    title: str
    lines: tuple[SummaryLine, ...]

    @property
    def is_empty(self) -> bool:
        return not self.lines


@dataclass(frozen=True, slots=True)
class ClinicalSummary:
    """The full draft. `render_text` produces the plain-text physician view; the
    API serialises the structure so a UI can render evidence links."""

    intake_id: str
    sections: tuple[SummarySection, ...]
    unresolved: tuple[SummaryLine, ...] = field(default_factory=tuple)
    conflicts: tuple[Contradiction, ...] = field(default_factory=tuple)
    alerts: tuple[RedFlagAlert, ...] = field(default_factory=tuple)
    coverage_percentage: float = 0.0
    physician_verified: bool = False

    def all_fact_ids(self) -> tuple[FactId, ...]:
        return tuple(
            fid for section in self.sections for line in section.lines for fid in line.fact_ids
        )

    def render_text(self) -> str:
        """Plain-text report in standard clinical order."""
        out: list[str] = [HEADER_DISCLAIMER, ""]
        for section in self.sections:
            out.append(section.title.upper())
            if section.is_empty:
                out.append(f"  {NOTHING_RECORDED_LINE}")
            else:
                out.extend(f"  - {line.text}" for line in section.lines)
            out.append("")

        out.append(UNRESOLVED_TITLE.upper())
        if self.unresolved:
            out.extend(f"  - {line.text}" for line in self.unresolved)
        else:
            out.append("  Nothing outstanding.")
        out.append("")

        out.append(CONFLICTS_TITLE.upper())
        if self.conflicts:
            for conflict in self.conflicts:
                out.extend(f"  {line}" for line in conflict.render().splitlines())
        else:
            out.append(f"  {NO_CONFLICTS_LINE}")
        out.append("")

        out.append(SAFETY_TITLE.upper())
        if self.alerts:
            for alert in self.alerts:
                state = (
                    f"acknowledged by {alert.acknowledged_by}"
                    if alert.is_acknowledged
                    else "awaiting acknowledgement"
                )
                out.append(f"  - [{alert.severity}] {alert.label} ({alert.rule_id}) — {state}")
                out.append(f"      basis: {alert.criteria_description}")
                out.append(f"      source: {alert.clinical_source}")
        else:
            out.append(f"  {NO_ALERTS_LINE}")
        out.append("")

        out.append(f"Coverage: {self.coverage_percentage}% of required fields.")
        out.append(FOOTER_DISCLAIMER)
        return "\n".join(out)

    def unsupported_assertions(self) -> tuple[str, ...]:
        """Forbidden phrases anywhere in the rendered report. Must always be empty."""
        return find_unsupported_assertions(self.render_text())


def _line_for(fact: ClinicalFact) -> SummaryLine:
    """Render one fact, preserving its original expression and its qualifiers."""
    label = fact.concept.display or fact.concept.concept_id.replace("_", " ")
    rendered = fact.rendered_value()

    if fact.status is FactStatus.ABSENT:
        text = f"Denies {label}"
    elif fact.status is FactStatus.UNKNOWN:
        text = f"{label}: patient unsure"
    elif rendered is not None:
        text = f"{label}: {rendered}"
    else:
        text = label

    text += annotate(fact.certainty, fact.reported_by, fact.physician_verified)
    if fact.original_expression:
        lang = f" / {fact.original_language}" if fact.original_language else ""
        text += f' (patient said: "{fact.original_expression}"{lang})'

    return SummaryLine(
        text=text,
        fact_ids=(fact.fact_id,),
        original_expression=fact.original_expression,
        original_language=fact.original_language,
    )


#: Marker written on a fact that restates another one. The source fact is not
#: rendered separately — printing both "Chest pain" and "Chief complaint:
#: chest_pain" says the same thing twice, once in the patient's language and once
#: in the system's.
_DERIVED_FROM = "derived from "


def _restated_concepts(facts: Sequence[ClinicalFact]) -> frozenset[str]:
    """Concepts that another live fact already restates more readably."""
    sources: set[str] = set()
    for fact in facts:
        if fact.note and fact.note.startswith(_DERIVED_FROM):
            source = fact.note[len(_DERIVED_FROM) :].split("=", 1)[0].strip()
            if source:
                sources.add(source)
    return frozenset(sources)


def _sort_facts(facts: Sequence[ClinicalFact]) -> tuple[ClinicalFact, ...]:
    """Positive findings first, then denials, then unknowns; stable within groups.

    A physician skims for what is there before what is not.
    """
    order = {FactStatus.PRESENT: 0, FactStatus.ABSENT: 1, FactStatus.UNKNOWN: 2}
    return tuple(sorted(facts, key=lambda f: (order.get(f.status, 3), f.concept.concept_id)))


def build(
    state: PatientIntakeState,
    *,
    coverage: CoverageReport,
    conflicts: Sequence[Contradiction] = (),
    alerts: Sequence[RedFlagAlert] = (),
) -> ClinicalSummary:
    """Assemble the summary. Pure: no clock, no I/O, no model."""
    restated = _restated_concepts(state.current())
    sections: list[SummarySection] = []
    for section in REPORT_SECTIONS:
        facts = [
            f
            for f in state.facts_for(section)
            if f.status not in {FactStatus.NOT_ASKED, FactStatus.NOT_APPLICABLE}
            and f.concept.concept_id not in restated
        ]
        if section is Section.AYURVEDA and not state.ayurveda_enabled:
            continue
        sections.append(
            SummarySection(
                section=section,
                title=SECTION_TITLES[section],
                lines=tuple(_line_for(f) for f in _sort_facts(facts)),
            )
        )

    unresolved: list[SummaryLine] = [
        SummaryLine(text=missing.describe()) for missing in coverage.missing()
    ]
    unresolved.extend(
        SummaryLine(
            text=f"{concept.replace('_', ' ')} — patient declined to answer",
        )
        for concept in sorted(state.declined)
    )
    unresolved.extend(
        SummaryLine(
            text=(
                f"{document.document_id} uploaded but not processed"
                if not document.processed
                else f"{document.document_id} extracted with low confidence "
                "— verify against the original"
            ),
            fact_ids=(),
        )
        for document in state.documents
        if not document.processed or document.low_confidence
    )

    return ClinicalSummary(
        intake_id=str(state.intake_id),
        sections=tuple(sections),
        unresolved=tuple(unresolved),
        conflicts=tuple(conflicts),
        alerts=tuple(alerts),
        coverage_percentage=coverage.percentage,
        physician_verified=all(f.physician_verified for f in state.current())
        if state.current()
        else False,
    )
