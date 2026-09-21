"""The timeline pure code can build on its own.

**This is the one that ships.** With no provider configured — the default — the
report still carries a dated, ordered history, which is the spec's
timeline requirement met with zero model risk. The provider, when one is turned
on, only ever *narrows* this set to what relates to today's complaint; it can
never add an event pure code did not already find.

That ordering matters more than it looks. It means the failure mode of the whole
timeline feature is "the physician sees more history than they needed", not "the
physician sees something that never happened".

Pure. No provider, no session, no clock.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from app.domain.clinical.enums import Section
from app.domain.documents.extraction import DocumentExtraction, DocumentItem, ItemKind
from app.domain.record import CanonicalRecord, FieldStatus
from app.domain.timeline.model import (
    ClinicalEvent,
    EventKind,
    TimelineCandidate,
    TimelineSnapshot,
    TimelineSource,
    TimelineStatus,
)
from app.domain.timeline.validate import order_events

#: What a prior visit contributes, if the record says nothing more specific.
_VISIT_LABEL_FALLBACK = "Consultation"


def _complaint_label(record: CanonicalRecord) -> str:
    """The visit's complaint, as a short label.

    The coded value rather than the patient's own words: those are theirs, are
    already shown verbatim on the visit they belong to, and reproducing them in
    a one-line timeline entry strips the context that made them readable.
    """
    for fact in record.live_facts():
        if fact.field_id != "chief_complaint" and not fact.field_id.endswith(
            ".chief_complaint"
        ):
            continue
        if fact.status is not FieldStatus.ANSWERED:
            continue
        rendered = fact.rendered_value()
        if rendered:
            return str(rendered)
    return _VISIT_LABEL_FALLBACK


def _visit_date(record: CanonicalRecord) -> date | None:
    when = record.completed_at or record.started_at or record.created_at
    return when.date() if when else None


def _tags_for(record: CanonicalRecord) -> tuple[str, ...]:
    """Coded values a reader — or a model — can judge relatedness on.

    Codes only. The patient's own words are not tags: they are evidence, they
    belong to the visit they were said at, and they are not a category.
    """
    tags: list[str] = []
    for fact in record.live_facts():
        if fact.status is not FieldStatus.ANSWERED:
            continue
        if fact.section not in {
            Section.CHIEF_COMPLAINT,
            Section.PAST_MEDICAL,
            Section.MEDICATIONS,
        }:
            continue
        rendered = fact.rendered_value()
        if rendered:
            tags.append(f"{fact.field_id}={rendered}")
    return tuple(sorted(set(tags)))


def candidates_from(
    prior: Sequence[CanonicalRecord],
    extractions: Sequence[DocumentExtraction] = (),
) -> tuple[TimelineCandidate, ...]:
    """Everything datable in the prior records, under short opaque ids.

    Sorted newest-first *before* the ids are assigned, so `c1` is the most
    recent thing on every run and a fixture keyed by scenario stays valid.

    An undated document is not a candidate. It cannot be placed on a timeline,
    and guessing a date to place it is the single worst thing this feature could
    do — the document timeline section already reports it as undated, which is
    the honest place for it.
    """
    found: list[tuple[date, EventKind, str, str | None, str | None, tuple[str, ...]]] = []

    for record in prior:
        when = _visit_date(record)
        if when is None:
            continue
        found.append(
            (
                when,
                EventKind.VISIT,
                _complaint_label(record),
                str(record.intake_id),
                None,
                _tags_for(record),
            )
        )

    for extraction in extractions:
        if extraction.document_date is None:
            continue
        for item in extraction.items:
            label = _item_label(item)
            if label is None:
                continue
            found.append(
                (
                    extraction.document_date,
                    _item_kind(item),
                    label,
                    None,
                    extraction.document_id,
                    (),
                )
            )

    found.sort(key=lambda row: (-row[0].toordinal(), row[1].value, row[2]))
    return tuple(
        TimelineCandidate(
            candidate_id=f"c{index + 1}",
            event_date=when,
            kind=kind,
            label=label,
            intake_id=intake_id,
            document_id=document_id,
            tags=tags,
        )
        for index, (when, kind, label, intake_id, document_id, tags) in enumerate(found)
    )


def _item_kind(item: DocumentItem) -> EventKind:
    if item.kind is ItemKind.MEDICINE:
        return EventKind.MEDICATION
    if item.kind is ItemKind.LAB_RESULT:
        return EventKind.INVESTIGATION
    return EventKind.DOCUMENT


def _item_label(item: DocumentItem) -> str | None:
    """A short label for one extracted line, or None when it has none.

    The extractor's own text, never a rephrasing of it. A line with nothing
    nameable on it is skipped rather than given a placeholder: "Other entry, 12
    June" on a physician's timeline is noise that costs attention and carries no
    information.
    """
    if item.medicine is not None:
        return item.medicine.name
    if item.lab_result is not None:
        return item.lab_result.analyte
    if item.label:
        return item.label
    return None


def deterministic_timeline(
    prior: Sequence[CanonicalRecord],
    extractions: Sequence[DocumentExtraction] = (),
    *,
    max_events: int = 12,
) -> TimelineSnapshot:
    """Every dated thing in the record, newest first. No model, no judgement.

    `UNFILTERED` is the status, and the report says so: this is the patient's
    history, not a selection from it, and a reader must not mistake the absence
    of filtering for a judgement that everything here is relevant.
    """
    candidates = candidates_from(prior, extractions)
    events = order_events(
        [
            ClinicalEvent(
                event_date=candidate.event_date,
                kind=candidate.kind,
                label=candidate.label,
                source=TimelineSource.DETERMINISTIC,
                intake_id=candidate.intake_id,
                document_id=candidate.document_id,
                candidate_id=candidate.candidate_id,
                relevance=1.0,
            )
            for candidate in candidates
        ]
    )
    return TimelineSnapshot(
        status=TimelineStatus.UNFILTERED,
        events=events[:max_events],
        # Truncation is not filtering. What fell off the end was dropped for
        # length, and saying "2 events judged unrelated" about it would be a
        # claim nobody made.
        omitted_count=max(len(events) - max_events, 0),
        provider=None,
    )
