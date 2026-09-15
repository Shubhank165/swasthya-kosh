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

from app.domain.ayush_profile import AyushProfileSnapshot
from app.domain.clinical.enums import SECTION_ORDER, Certainty, ReporterRole, Section
from app.domain.clinical.sections import DEFAULT_SECTION, section_for
from app.domain.documents.extraction import (
    DocumentExtraction,
    DocumentItem,
    ItemKind,
    RangeStatus,
)
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
from app.domain.timeline.model import TimelineSnapshot, TimelineStatus

#: 1.1 adds the DOCUMENT TIMELINE section; 1.2 adds HISTORY TIMELINE.
TEMPLATE_VERSION = "1.2"

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


def _effective_section(fact: Fact) -> Section:
    """Where this fact renders, which is not always where it was filed.

    Two corrections, and both exist because a section is decided at ingest and
    read back months later.

    A **chief-complaint** field always renders as one. Content built on a
    different question set can file the same clinical fact under a routing or
    triage field — the deployed app bundle's `routing.chief_complaint` lands in
    HPI (2026-09-11) — and a physician opening the report to a header that says
    "Nothing recorded" while the actual complaint sits a section down is worse
    than a content bug: it reads as no complaint was ever taken. Matched on
    field id suffix rather than an exact string so any
    `<namespace>.chief_complaint` field is covered without a content change.

    A fact filed under the **fallback** section is re-looked-up against the
    current table. `DEFAULT_SECTION` is what an unrecognised field id gets, so
    it means "nothing knew where this went" rather than "a physician's answer
    belongs in the history of the presenting illness" — and every app-bundle
    field id was unrecognised until the table learned them, which put age,
    family history and the whole Ayurveda assessment into HPI. Re-deriving here
    repairs intakes already in the database; re-ingesting them is not an option
    and leaving them unreadable is not either.

    A section the device or the table genuinely chose is never overridden. The
    stored `fact.section` is untouched either way: this changes where a line
    prints, not what was recorded.
    """
    field_id = fact.field_id
    if field_id == "chief_complaint" or field_id.endswith(".chief_complaint"):
        return Section.CHIEF_COMPLAINT
    if fact.section is DEFAULT_SECTION:
        return section_for(field_id)
    return fact.section


def _ayush_lines(
    profile: AyushProfileSnapshot, labels: FieldLabels
) -> tuple[ReportLine, ...]:
    """The AYUSH/Prakriti self-report as lines of the Ayurveda section.

    **Answered fields only**, and in field-id order so the section is
    byte-stable across reads. A profile is answered in one sitting rather than
    accumulated across an interview, so the unsettled ones carry none of the
    meaning they carry for a visit: "not asked" on question 40 of a module the
    patient closed halfway is not a gap a physician has to finish, and putting
    sixty such lines under UNRESOLVED would bury the ones that are.

    No `fact_ids` and no `sources`: these are not facts in this intake's
    record. They come from the patient's profile, which is a different thing
    with a different lifetime, and claiming a fact id would invite the evidence
    endpoint to look for a row that does not exist.
    """
    lines: list[ReportLine] = []
    for answer in sorted(profile.answers, key=lambda a: a.field_id):
        if answer.status != FieldStatus.ANSWERED.value or answer.value is None:
            continue
        label = labels(answer.field_id)
        rendered = _ayush_value(answer.value)
        if rendered is None:
            continue
        text = f"{label}: {rendered}"
        if answer.original_text:
            text += " (" + answer.original_text + ")"
        lines.append(
            ReportLine(
                text=text,
                label=label,
                value=rendered,
                field_ids=(answer.field_id,),
                original_text=answer.original_text,
                original_language=profile.language,
            )
        )
    return tuple(lines)


def _ayush_value(value: object) -> str | None:
    """A stored answer as display text.

    Deliberately literal. A coded answer prints its code where no label was
    found rather than a prettified guess, for the reason the rest of this
    module gives: a report that improves on what it was given is a report that
    says something nobody said.
    """
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float, str)):
        return str(value)
    if isinstance(value, list):
        parts = [_ayush_value(item) for item in value]
        kept = [p for p in parts if p]
        return ", ".join(kept) if kept else None
    if isinstance(value, dict):
        # `{"n": 3, "unit": "day"}` and friends — the shapes `AnswerValue`
        # produces. Rendered as the pair they are, not flattened to a number.
        n, unit = value.get("n"), value.get("unit")
        if n is not None and unit:
            return f"{n} {unit}"
        code = value.get("value")
        return str(code) if code is not None else None
    return None


def _line_for(fact: Fact, templates: TemplateSet, labels: FieldLabels) -> ReportLine:
    """One answered fact as one line."""
    label = labels(fact.field_id)
    value: str | None
    if fact.denies():
        text = templates.format("denies", field=label)
        # "Denies fever" is one statement, not a label and a value. Saying
        # otherwise would let a screen print "Fever — denies fever".
        value = None
    else:
        rendered = fact.rendered_value()
        text = f"{label}: {rendered}" if rendered is not None else label
        value = rendered

    if fact.original_text:
        # Verbatim, in the script it was spoken in. Printed beside the
        # normalised term rather than instead of it, so the physician can see
        # both what was said and what we made of it.
        text += " (" + templates.format("patient_said", text=fact.original_text) + ")"

    return ReportLine(
        text=text,
        label=label,
        value=value,
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

    `NOT_APPLICABLE` is kept here even though `build` no longer sends it: this
    is a renderer, and a renderer that silently mislabels a status it was handed
    is a worse failure than one branch that the current caller does not reach.
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


#: Which report section a *classified* document item lands in. Mirrors
#: `_fact_shape` in `app.services.documents`, because an item and the fact
#: derived from it should appear in the same place — a medicine read off a
#: prescription is drug history, not an investigation.
#:
#: `ItemKind.OTHER` has no entry on purpose. It means "read, understood as
#: text, but not classified" (`app.domain.documents.extraction`) — a form's
#: letterhead, a doctor's signature line and a patient's date of birth are all
#: `OTHER` alongside anything genuinely clinical the model could not place, and
#: none of the three is a prior investigation. Filing it there anyway is what
#: produced a PRIOR INVESTIGATIONS section made of "Doctor Name" and "Father's
#: Name" from a bed-rest certificate (2026-09-11). `_unclassified_lines` below
#: gives it a home that does not claim to be a clinical section.
_ITEM_SECTIONS: Mapping[ItemKind, Section] = {
    ItemKind.MEDICINE: Section.MEDICATIONS,
    ItemKind.DIAGNOSIS: Section.PAST_MEDICAL,
    ItemKind.PROCEDURE: Section.PAST_SURGICAL,
    ItemKind.LAB_RESULT: Section.INVESTIGATIONS,
}


def _rendered_item_text(
    item: DocumentItem, extraction: DocumentExtraction, templates: TemplateSet
) -> str:
    """The line for one classified item: its value, any range flag, the raw
    text beside a low-confidence read, and the document it came from."""
    text = item.render()
    if item.range_status is RangeStatus.BELOW_RANGE:
        text += f" — {templates.text('range_below')}"
    elif item.range_status is RangeStatus.ABOVE_RANGE:
        text += f" — {templates.text('range_above')}"
    elif item.lab_result is not None and item.range_status is RangeStatus.RANGE_UNAVAILABLE:
        text += f" — {templates.text('range_unavailable')}"
    if item.needs_verification and item.raw_text:
        text += " (" + templates.format("patient_said", text=item.raw_text) + ")"
    # The source label goes on the line so a physician reading "Metformin
    # 500 mg BD" in the drug history can tell it came off a scan rather than
    # out of the patient's mouth.
    text += f" [{extraction.document_id} p{item.page}]"
    return text


def _document_lines(
    extractions: Sequence[DocumentExtraction], templates: TemplateSet
) -> dict[Section, list[ReportLine]]:
    """Every *classified* item read off the patient's documents, grouped by
    report section. Unclassified (`OTHER`) items are handled separately by
    `_unclassified_lines` — see the note on `_ITEM_SECTIONS`.

    Lab results carry the reference range printed on their own document and,
    where one existed, a statement of where the value sits against it. A result
    with no printed range says so and is not flagged — see
    `app.domain.documents.labs`.
    """
    grouped: dict[Section, list[ReportLine]] = {}
    for extraction in sorted(extractions, key=lambda e: e.document_id):
        for item in extraction.items:
            section = _ITEM_SECTIONS.get(item.kind)
            if section is None:
                continue
            markers: list[LineMarker] = []
            if item.needs_verification:
                markers.append(
                    LineMarker(code="verify", text=templates.text("verify_marker"))
                )
            grouped.setdefault(section, []).append(
                ReportLine(
                    text=_rendered_item_text(item, extraction, templates),
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


def _unclassified_lines(
    extractions: Sequence[DocumentExtraction], templates: TemplateSet
) -> tuple[ReportLine, ...]:
    """`OTHER` items: text the OCR pass read but could not — or should not —
    place in a clinical section. Shown plainly as unclassified rather than
    silently dropped (§6.3) or, worse, dressed up as a finding."""
    lines: list[ReportLine] = []
    for extraction in sorted(extractions, key=lambda e: e.document_id):
        for item in extraction.items:
            if item.kind is not ItemKind.OTHER:
                continue
            shown = item.raw_text or item.label or ""
            if not shown.strip():
                continue
            lines.append(
                ReportLine(
                    text=templates.format(
                        "document_other_text",
                        document=f"{extraction.document_id} p{item.page}",
                        text=shown,
                    ),
                    field_ids=(f"document_item:{item.kind}",),
                    fact_ids=(item.item_id,),
                    sources=(
                        DocumentSource(
                            document_id=extraction.document_id,
                            page=item.page,
                            bbox=item.bbox,
                        ),
                    ),
                )
            )
    return tuple(lines)


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
    timeline: TimelineSnapshot | None = None,
    ayush_profile: AyushProfileSnapshot | None = None,
    labels: FieldLabels = DEFAULT_LABELS,
    demo: bool = False,
) -> PhysicianReport:
    """Assemble the report. Pure.

    `timeline` arrives as a finished value, exactly as `extractions` do. The
    builder never fetches it and never calls anything to produce it — that is
    what keeps this module model-free while the timeline's *contents* may have
    been selected by one upstream. Each event renders through `templates.format`
    like every other line: the model extracts, the templates render.
    """
    labels = labels.overlaid(templates.labels)
    live = record.live_facts()
    voice = [f for f in live if f.is_from_today]

    document_lines = _document_lines(extractions, templates)

    sections: list[ReportSection] = []
    for section in BODY_SECTIONS:
        answered = [
            f
            for f in voice
            if _effective_section(f) is section and f.status is FieldStatus.ANSWERED
        ]
        lines = [_line_for(f, templates, labels) for f in _sort_facts(answered)]
        lines.extend(document_lines.get(section, ()))
        # The patient-level module, which has no facts in this intake's record
        # and so cannot arrive through `voice`. Appended rather than given a
        # section of its own: a Vaidya reading AYURVEDA wants the constitution
        # and today's answers in one place, and two adjacent sections with
        # similar titles is how a reader learns to skip one.
        if section is Section.AYURVEDA and ayush_profile is not None:
            lines.extend(_ayush_lines(ayush_profile, labels))
        sections.append(
            ReportSection(
                section=section, title=templates.title(section), lines=tuple(lines)
            )
        )

    # Everything that did not settle, in field order — except the fields that
    # never applied.
    #
    # A gap and an exclusion are different findings. "Allergies — not
    # established" is work a physician has to finish; "Last menstrual period —
    # not applicable" on a male patient with a headache is the interview
    # working correctly. One real intake produced fifty-five unresolved lines of
    # which fifty-one were the second kind, burying the four of the first, and a
    # section a physician learns to skip is worse than no section.
    #
    # `NOT_APPLICABLE` is dropped from the report only. The fact keeps its
    # status in the record, the evidence endpoint still returns it, and the FHIR
    # export is untouched — what was considered and excluded stays recoverable,
    # it just stops competing for attention on the page.
    unsettled = sorted(
        (
            f
            for f in voice
            if f.status is not FieldStatus.ANSWERED
            and f.status is not FieldStatus.NOT_APPLICABLE
        ),
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

    # Sorted, because this dict is serialised into the report and the report is
    # byte-deterministic.
    mentioned = {f.field_id for f in live} | {c.field_id for c in record.contradictions}

    return PhysicianReport(
        intake_id=str(record.intake_id),
        hospital_id=record.hospital_id,
        language=templates.language,
        template_version=TEMPLATE_VERSION,
        field_labels={fid: labels(fid) for fid in sorted(mentioned)},
        sections=tuple(sections),
        unresolved=unresolved,
        conflicts=tuple(record.contradictions),
        alerts=tuple(record.red_flags),
        interactions=interaction_lines,
        document_timeline=_document_timeline(record, extractions, templates),
        document_notes=_document_notes(record, templates)
        + _unclassified_lines(extractions, templates),
        history=timeline,
        contains_repaired=any(f.repaired for f in live),
        needs_verification=any(f.needs_verification for f in live)
        or any(e.low_confidence for e in extractions),
        demo=demo,
        generated_at=record.updated_at,
    )


def _history_lines(report: PhysicianReport, templates: TemplateSet) -> list[str]:
    """The history timeline, with the state it is in stated on every path.

    Three states and three different sentences, because a reader cannot tell
    them apart from the list alone: *not built yet* is not *nothing on record*,
    and *everything on record* is not *what we judged relevant*. A filtered
    timeline that does not announce it is filtered reads as a complete history
    and is not — which is the whole reason `history_filtered_note` exists and
    is not optional decoration.
    """
    timeline = report.history
    if timeline is None or timeline.status is TimelineStatus.PENDING:
        # Never a silently empty section. "Not ready" and "nothing there" look
        # identical on screen and mean opposite things.
        return [templates.text("history_pending")]

    if not timeline.events:
        return [templates.text("history_none")]

    lines = [
        templates.format(
            "history_event",
            date=event.event_date.isoformat(),
            label=event.label,
        )
        for event in timeline.events
    ]
    if timeline.status is TimelineStatus.FILTERED:
        lines.append(
            templates.format("history_filtered_note", omitted=timeline.omitted_count)
        )
    else:
        lines.append(templates.text("history_unfiltered"))
    return lines


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

    # Immediately before the document timeline, and deliberately *not* merged
    # into it: that section answers how stale each uploaded scan is, and
    # "this scan is 40 days old" beside "3 Aug 2026 — Metformin started" makes
    # both harder to read than either alone.
    out.append(templates.text("history_title").upper())
    out.extend(f"  {line}" for line in _history_lines(report, templates))
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
            heading = report.field_labels.get(conflict.field_id) or conflict.field_id.replace(
                "_", " "
            )
            out.append(f"  {heading}")
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
