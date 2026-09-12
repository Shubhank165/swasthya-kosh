"""The gate between a model's proposals and a physician's screen.

**Pure. No I/O, no provider, no clock.** Every guarantee this feature makes about
model output is enforced here, which is why it is a module a reader can hold in
their head and a test file can exhaust.

Four rules, in order:

1. An event whose `candidate_id` is not one of the candidates offered is
   dropped. It was not selected from the record; it was invented.
2. An event whose date disagrees with its candidate's is dropped. A real event
   moved to a wrong date is worse than a missing one — a physician reads the
   order as causation.
3. An event below the relevance floor is dropped, and one with no
   `relevance_reason` with it: "related because it is also a knee" is checkable,
   an unexplained 0.9 is not.
4. What survives is truncated to the cap and sorted, newest first, so a chatty
   model cannot lengthen the report and two runs cannot disagree about order.

The label is taken from the *candidate*, not from the model's echo of it. That
single line is what makes "selects, never authors" true rather than instructed:
a model that rewrites a label into something more clinical-sounding has its
rewrite discarded.
"""

from __future__ import annotations

from app.domain.timeline.model import (
    ClinicalEvent,
    TimelineCandidate,
    TimelineDraft,
    TimelineSource,
)

#: Twelve words, matching the instruction the provider is given. A longer label
#: is a sentence, and a sentence is prose somebody wrote.
MAX_LABEL_WORDS = 12


def _shorten(label: str) -> str:
    words = label.split()
    if len(words) <= MAX_LABEL_WORDS:
        return label.strip()
    return " ".join(words[:MAX_LABEL_WORDS])


def validated_events(
    draft: TimelineDraft,
    *,
    candidates: tuple[TimelineCandidate, ...],
    min_relevance: float,
    max_events: int,
) -> tuple[tuple[ClinicalEvent, ...], int]:
    """The events fit to render, and how many were left out.

    The count returned is computed here rather than taken from the draft: a
    model that drops an event without saying so would otherwise make the report
    understate the gap, and "3 earlier events are not shown" is the line that
    stops a filtered timeline reading as a complete history.
    """
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    kept: list[ClinicalEvent] = []
    seen: set[str] = set()

    for event in draft.events:
        candidate = by_id.get(event.candidate_id or "")
        if candidate is None:
            # Rule 1. Not selected from the record — invented.
            continue
        if event.event_date != candidate.event_date:
            # Rule 2. A real event on a wrong date reads as a cause.
            continue
        if event.relevance < min_relevance:
            continue
        if not (event.relevance_reason or "").strip():
            # An unexplained score is not a justification a reader can check.
            continue
        if candidate.candidate_id in seen:
            # One candidate, one line. A model repeating itself must not make
            # an event look like two occurrences.
            continue
        seen.add(candidate.candidate_id)
        kept.append(
            ClinicalEvent(
                event_date=candidate.event_date,
                kind=candidate.kind,
                # From the candidate, never the model's echo of it. This is
                # what makes "selects, never authors" a property.
                label=_shorten(candidate.label),
                source=TimelineSource.MODEL_SELECTED,
                intake_id=candidate.intake_id,
                document_id=candidate.document_id,
                candidate_id=candidate.candidate_id,
                relevance=min(max(event.relevance, 0.0), 1.0),
                relevance_reason=event.relevance_reason.strip()
                if event.relevance_reason
                else None,
            )
        )

    ordered = order_events(kept)[:max_events]
    return ordered, max(len(candidates) - len(ordered), 0)


def order_events(events: list[ClinicalEvent]) -> tuple[ClinicalEvent, ...]:
    """Newest first, and stable under a shuffled input.

    The tie-break runs all the way down to `candidate_id` so two events on one
    date cannot swap places between runs. The report is byte-deterministic and
    is pinned by golden files; an unstable sort here would make that a
    coin-toss.
    """
    return tuple(
        sorted(
            events,
            key=lambda event: (
                -event.event_date.toordinal(),
                event.kind.value,
                event.label,
                event.candidate_id or "",
            ),
        )
    )
