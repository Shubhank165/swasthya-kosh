"""Report assembly.

**Template. No model. No exceptions.**

A language model cannot write this document. Not because a model would write it
badly — it would write it fluently — but because fluent prose about a patient is
indistinguishable from fluent prose about a patient who does not exist, and
there is no way to check the difference at the speed a physician reads. Every
line here is a template filled from a fact, and every line carries the fact ids
it was filled from, so the difference is checkable by clicking.

Pure: no clock, no I/O, no database. The same `CanonicalRecord` renders
byte-identical output every time, which is what `tests/report/` asserts against
golden files.

The rendering rules that carry clinical weight:

- `unresolved`, `not_asked` and `refused` appear under **Unresolved**, worded as
  "not established". Never omitted, never rendered as absent, never as `no`.
- A repaired field renders with a marker and is never shown as confirmed.
- A low-confidence OCR value renders with a marker and the raw text alongside.
- A contradiction renders both claims side by side with equal weight and no
  winner.
- The patient's own words appear beside the normalised term, untranslated.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.domain.clinical.enums import SECTION_ORDER, Certainty, ReporterRole, Section
from app.domain.documents.extraction import DocumentExtraction, ItemKind, RangeStatus
from app.domain.documents.interactions import InteractionFinding
from app.domain.record import (
    CanonicalRecord,
    DocumentSource,
    DocumentStatus,
    Fact,
    FieldStatus,
    RedFlagEvent,
)
from app.domain.report.model import (
    InteractionLine,
    LineMarker,
    PhysicianReport,
    ReportLine,
    ReportSection,
    TimelineEntry,
)
from app.domain.report.templates import TemplateSet

#: 1.1 adds the DOCUMENT TIMELINE section.
TEMPLATE_VERSION = "1.1"

#: Sections that appear in the report body, in render order. Fixed by the
#: problem statement: chief complaint, HPI, past medical and surgical, drug and
#: allergy, family, personal, review of systems, prior investigations, the
#: Ayurveda patient-reported section, then unresolved, conflicts and safety.
BODY_SECTIONS: tuple[Section, ...] = tuple(
    s
    for s in SECTION_ORDER
    if s not in {Section.CONSENT, Section.IDENTITY}
)


class FieldLabels:
    """Field id -> the words a physician reads.

    Backed by the concept registry where a concept exists, and by a mechanical
    de-underscoring where one does not. An unmapped field is labelled, printed
    and left for a clinician to name — never dropped for want of a display
    string.
    """

    def __init__(self, labels: Mapping[str, str] | None = None) -> None:
        self._labels = dict(labels or {})

    def __call__(self, field_id: str) -> str:
        return self._labels.get(field_id) or field_id.replace("_", " ")

    def as_mapping(self) -> dict[str, str]:
        """The underlying map, for callers that need it as data."""
        return dict(self._labels)

    def overlaid(self, overrides: Mapping[str, str]) -> FieldLabels:
        """These labels with a language's translations layered on top.

        Partial by design. A field the language file does not name keeps its
        English display — a fallback a clinician can read, rather than a
        machine translation of a clinical term nobody reviewed.
        """
        return FieldLabels({**self._labels, **overrides})


DEFAULT_LABELS = FieldLabels()


# --- markers -----------------------------------------------------------------


def _markers_for(fact: Fact, templates: TemplateSet) -> tuple[LineMarker, ...]:
    """Every qualifier this fact has earned.

    Order is fixed so the rendering is deterministic, and it runs from "the
    machine is unsure" to "a person has not checked this yet".
    """
    markers: list[LineMarker] = []
    if fact.repaired:
        markers.append(LineMarker(code="repaired", text=templates.text("repaired_marker")))
    if fact.needs_verification:
        markers.append(LineMarker(code="verify", text=templates.text("verify_marker")))
    if fact.certainty is Certainty.APPROXIMATE:
        markers.append(
            LineMarker(code="approximate", text=templates.text("approximate_marker"))
        )
    elif fact.certainty is Certainty.UNCERTAIN:
        markers.append(LineMarker(code="uncertain", text=templates.text("uncertain_marker")))
    if fact.reported_by in {
        ReporterRole.FAMILY_ATTENDANT,
        ReporterRole.CAREGIVER,
        ReporterRole.PARENT_GUARDIAN,
    }:
        markers.append(LineMarker(code="attendant", text=templates.text("attendant_marker")))
    return tuple(markers)


def _line_for(fact: Fact, templates: TemplateSet, labels: FieldLabels) -> ReportLine:
    """One answered fact as one line."""
    label = labels(fact.field_id)
    if fact.denies():
        text = templates.format("denies", field=label)
    else:
        rendered = fact.rendered_value()
        text = f"{label}: {rendered}" if rendered is not None else label

    if fact.original_text:
        # Verbatim, in the script it was spoken in. Printed beside the
        # normalised term rather than instead of it, so the physician can see
        # both what was said and what we made of it.
        text += " (" + templates.format("patient_said", text=fact.original_text) + ")"

    return ReportLine(
        text=text,
        field_ids=(fact.field_id,),
        fact_ids=(fact.fact_id,),
        sources=(fact.source,),
        markers=_markers_for(fact, templates),
        original_text=fact.original_text,
        original_language=fact.language,
    )


def _unresolved_line(fact: Fact, templates: TemplateSet, labels: FieldLabels) -> ReportLine:
    """One unsettled field as one line under *Unresolved*.

    Three statuses, three different sentences. Collapsing them would throw away
    the distinction the whole record model exists to preserve: "we never asked",
    "we asked and could not pin it down" and "the patient declined" are three
    different things for a physician about to ask the same question.
    """
    label = labels(fact.field_id)
    key = {
        FieldStatus.REFUSED: "declined_to_answer",
        FieldStatus.NOT_APPLICABLE: "not_applicable",
    }.get(fact.status, "not_established")
    return ReportLine(
        text=templates.format(key, field=label),
        field_ids=(fact.field_id,),
        fact_ids=(fact.fact_id,),
        sources=(fact.source,),
        original_text=fact.original_text,
        original_language=fact.language,
    )


def _sort_facts(facts: Sequence[Fact]) -> tuple[Fact, ...]:
    """Positive findings first, then denials; stable within groups.

    A physician skims for what is there before what is not.
    """
    return tuple(
        sorted(facts, key=lambda f: (0 if not f.denies() else 1, f.field_id, f.fact_id))
    )


# --- documents ---------------------------------------------------------------


#: Which report section a document item lands in. Mirrors `_fact_shape` in
#: `app.services.documents`, because an item and the fact derived from it should
#: appear in the same place — a medicine read off a prescription is drug
#: history, not an investigation.
_ITEM_SECTIONS: Mapping[ItemKind, Section] = {
    ItemKind.MEDICINE: Section.MEDICATIONS,
    ItemKind.DIAGNOSIS: Section.PAST_MEDICAL,
    ItemKind.PROCEDURE: Section.PAST_SURGICAL,
    ItemKind.LAB_RESULT: Section.INVESTIGATIONS,
    ItemKind.OTHER: Section.INVESTIGATIONS,
}


def _document_lines(
    extractions: Sequence[DocumentExtraction], templates: TemplateSet
) -> dict[Section, list[ReportLine]]:
    """Everything read off the patient's documents, grouped by report section.

    Lab results carry the reference range printed on their own document and,
    where one existed, a statement of where the value sits against it. A result
    with no printed range says so and is not flagged — see
    `app.domain.documents.labs`.
    """
    grouped: dict[Section, list[ReportLine]] = {}
    for extraction in sorted(extractions, key=lambda e: e.document_id):
        for item in extraction.items:
            markers: list[LineMarker] = []
            if item.needs_verification:
                markers.append(
                    LineMarker(code="verify", text=templates.text("verify_marker"))
                )
            text = item.render()
            if item.range_status is RangeStatus.BELOW_RANGE:
                text += f" — {templates.text('range_below')}"
            elif item.range_status is RangeStatus.ABOVE_RANGE:
                text += f" — {templates.text('range_above')}"
            elif (
                item.lab_result is not None
                and item.range_status is RangeStatus.RANGE_UNAVAILABLE
            ):
                text += f" — {templates.text('range_unavailable')}"
            if item.needs_verification and item.raw_text:
                text += " (" + templates.format("patient_said", text=item.raw_text) + ")"
            # The source label goes on the line so a physician reading "Metformin
            # 500 mg BD" in the drug history can tell it came off a scan rather
            # than out of the patient's mouth.
            text += f" [{extraction.document_id} p{item.page}]"
            section = _ITEM_SECTIONS.get(item.kind, Section.INVESTIGATIONS)
            grouped.setdefault(section, []).append(
                ReportLine(
                    text=text,
                    field_ids=(f"document_item:{item.kind}",),
                    fact_ids=(item.item_id,),
                    sources=(
                        DocumentSource(
                            document_id=extraction.document_id,
                            page=item.page,
                            bbox=item.bbox,
                        ),
                    ),
                    markers=tuple(markers),
                )
            )
    return grouped


def _document_notes(record: CanonicalRecord, templates: TemplateSet) -> tuple[ReportLine, ...]:
    """A line for every document that did not come through cleanly.

    A document that failed the quality gate, is still processing, or was read
    with low confidence is stated on the report. Silence here would let a
    physician assume the prescription in the patient's hand had been read.
    """
    notes: list[ReportLine] = []
    for document in sorted(record.documents, key=lambda d: d.document_id):
        if document.status is DocumentStatus.REJECTED_QUALITY:
            notes.append(
                ReportLine(
                    text=templates.format(
                        "document_rejected",
                        document=document.document_id,
                        reason=document.rejection_reason or "unreadable",
                    ),
                    field_ids=(document.document_id,),
                )
            )
        elif not document.is_processed:
            notes.append(
                ReportLine(
                    text=templates.format(
                        "document_unprocessed", document=document.document_id
                    ),
                    field_ids=(document.document_id,),
                )
            )
        elif document.low_confidence:
            notes.append(
                ReportLine(
                    text=templates.format(
                        "document_low_confidence", document=document.document_id
                    ),
                    field_ids=(document.document_id,),
                    markers=(LineMarker(code="verify", text=templates.text("verify_marker")),),
                )
            )
    return tuple(notes)


def _document_timeline(
    record: CanonicalRecord,
    extractions: Sequence[DocumentExtraction],
    templates: TemplateSet,
) -> tuple[TimelineEntry, ...]:
    """Place every processed document in time relative to this intake.

    Anchored to when the patient finished the interview
    (`completed_at`, device-stamped; `created_at` only if that is somehow
    absent) — a field already on the record, never a live clock, so the report
    stays byte-deterministic. A document dated before that is historical by
    exactly the number of days stated; one with no legible date gets a line
    saying so, because "cannot be placed in time" is itself the finding a
    physician needs.
    """
    intake_day = (record.completed_at or record.created_at).date()
    entries: list[TimelineEntry] = []
    for extraction in sorted(extractions, key=lambda e: e.document_id):
        if extraction.was_rejected:
            continue
        fact_ids = tuple(
            f.fact_id
            for f in record.live_facts()
            if isinstance(f.source, DocumentSource)
            and f.source.document_id == extraction.document_id
        )
        doc_date = extraction.document_date
        if doc_date is None:
            entries.append(
                TimelineEntry(
                    document_id=extraction.document_id,
                    dated=False,
                    text=templates.format(
                        "timeline_undated", document=extraction.document_id
                    ),
                    fact_ids=fact_ids,
                )
            )
            continue
        days = (intake_day - doc_date).days
        key = "timeline_future" if days < 0 else "timeline_dated"
        entries.append(
            TimelineEntry(
                document_id=extraction.document_id,
                document_date=doc_date,
                days_before_intake=days,
                dated=True,
                text=templates.format(
                    key,
                    document=extraction.document_id,
                    date=doc_date.isoformat(),
                    days=abs(days),
                ),
                fact_ids=fact_ids,
            )
        )
    return tuple(entries)


# --- assembly ----------------------------------------------------------------


def build(
    record: CanonicalRecord,
    *,
    templates: TemplateSet,
    extractions: Sequence[DocumentExtraction] = (),
    interactions: Sequence[InteractionFinding] = (),
    labels: FieldLabels = DEFAULT_LABELS,
    demo: bool = False,
) -> PhysicianReport:
    """Assemble the report. Pure."""
    labels = labels.overlaid(templates.labels)
    live = record.live_facts()
    voice = [f for f in live if f.is_from_today]

    document_lines = _document_lines(extractions, templates)

    sections: list[ReportSection] = []
    for section in BODY_SECTIONS:
        answered = [
            f for f in voice if f.section is section and f.status is FieldStatus.ANSWERED
        ]
        lines = [_line_for(f, templates, labels) for f in _sort_facts(answered)]
        lines.extend(document_lines.get(section, ()))
        sections.append(
            ReportSection(
                section=section, title=templates.title(section), lines=tuple(lines)
            )
        )

    # Everything that did not settle, in field order. Nothing is omitted: a
    # field the interview never reached is as much a finding as one it did.
    unsettled = sorted(
        (f for f in voice if f.status is not FieldStatus.ANSWERED),
        key=lambda f: (f.field_id, f.fact_id),
    )
    unresolved = tuple(_unresolved_line(f, templates, labels) for f in unsettled)

    interaction_lines = tuple(
        InteractionLine(
            text=f"{finding.left_display} + {finding.right_display} — {finding.rule.effect}. "
            + templates.text("interaction_prompt"),
            severity=finding.rule.severity.value,
            source=finding.rule.source,
        )
        for finding in interactions
    )

    return PhysicianReport(
        intake_id=str(record.intake_id),
        hospital_id=record.hospital_id,
        language=templates.language,
        template_version=TEMPLATE_VERSION,
        sections=tuple(sections),
        unresolved=unresolved,
        conflicts=tuple(record.contradictions),
        alerts=tuple(record.red_flags),
        interactions=interaction_lines,
        document_timeline=_document_timeline(record, extractions, templates),
        document_notes=_document_notes(record, templates),
        contains_repaired=any(f.repaired for f in live),
        needs_verification=any(f.needs_verification for f in live)
        or any(e.low_confidence for e in extractions),
        demo=demo,
        generated_at=record.updated_at,
    )


# --- rendering ---------------------------------------------------------------


def render_text(report: PhysicianReport, templates: TemplateSet) -> str:
    """The plain-text physician view.

    Deterministic to the byte. Section order, line order and marker order are
    all fixed above; nothing here consults a clock, a set or a dict iteration
    order that could vary between runs.
    """
    out: list[str] = []
    if report.demo:
        out.append(templates.text("demo_banner"))
    out.extend([templates.text("header_disclaimer"), ""])

    for section in report.sections:
        out.append(section.title.upper())
        if section.is_empty:
            out.append(f"  {templates.text('nothing_recorded')}")
        else:
            out.extend(f"  - {line.rendered()}" for line in section.lines)
        out.append("")

    out.append(templates.text("unresolved_title").upper())
    if report.unresolved:
        out.extend(f"  - {line.rendered()}" for line in report.unresolved)
    else:
        out.append(f"  {templates.text('nothing_outstanding')}")
    if report.document_notes:
        out.extend(f"  - {line.rendered()}" for line in report.document_notes)
    out.append("")

    out.append(templates.text("timeline_title").upper())
    if report.document_timeline:
        out.extend(f"  - {entry.text}" for entry in report.document_timeline)
    else:
        out.append(f"  {templates.text('timeline_none')}")
    out.append("")

    out.append(templates.text("conflicts_title").upper())
    if report.conflicts:
        for conflict in report.conflicts:
            today = conflict.reported_today
            out.append(f"  {conflict.field_id.replace('_', ' ')}")
            out.append(
                f"    {templates.text('conflict_today'):<16}: "
                + (
                    f"{today.statement} [{today.source_label}]"
                    if today is not None
                    else templates.text("conflict_not_mentioned")
                )
            )
            out.append(
                f"    {templates.text('conflict_record'):<16}: "
                f"{conflict.from_record.statement} [{conflict.from_record.source_label}]"
            )
            out.append(f"    -> {templates.text('conflict_resolution')}")
    else:
        out.append(f"  {templates.text('no_conflicts')}")
    out.append("")

    out.append(templates.text("interactions_title").upper())
    if report.interactions:
        for interaction in report.interactions:
            out.append(f"  - {interaction.text}")
            out.append(f"      source: {interaction.source}")
    else:
        out.append(f"  {templates.text('no_interactions')}")
    out.append("")

    out.append(templates.text("safety_title").upper())
    if report.alerts:
        for alert in sorted(report.alerts, key=lambda a: a.rule_id):
            out.append(f"  - [{alert.severity}] {_alert_label(alert)} ({alert.rule_id})")
            out.append(f"      {_alert_state(alert, templates)}")
            if alert.criteria_met:
                out.append(f"      basis: {', '.join(alert.criteria_met)}")
    else:
        out.append(f"  {templates.text('no_alerts')}")
    out.append("")

    out.append(templates.text("footer_disclaimer"))
    return "\n".join(out)


def _alert_label(alert: RedFlagEvent) -> str:
    return alert.label or alert.rule_id.replace("_", " ").lower()


def _alert_state(alert: RedFlagEvent, templates: TemplateSet) -> str:
    if alert.acknowledged_by is None:
        return templates.text("alert_awaiting")
    return templates.format("alert_acknowledged", actor=alert.acknowledged_by)
