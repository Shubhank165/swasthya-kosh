"""The gate between a model's proposals and a physician's screen.

**Pure. No provider, no session, no clock.** Every guarantee the timeline feature
makes about model output is enforced in `validate.py`, so it can be exhausted
here rather than argued about in a design document.

The case that names the whole problem is at the bottom: a foot injury offered as
relevant to a fever complaint. That is the user's own example, and the answer is
not "the model is usually sensible" — it is that a score below the floor is
dropped by code that cannot be talked round.
"""

from __future__ import annotations

import random
from datetime import date

from app.domain.timeline.model import (
    ClinicalEvent,
    EventKind,
    TimelineCandidate,
    TimelineDraft,
    TimelineSource,
)
from app.domain.timeline.validate import order_events, validated_events

CANDIDATES = (
    TimelineCandidate(
        candidate_id="c1",
        event_date=date(2026, 8, 14),
        kind=EventKind.VISIT,
        label="Fever, five days",
    ),
    TimelineCandidate(
        candidate_id="c2",
        event_date=date(2026, 6, 2),
        kind=EventKind.MEDICATION,
        label="Metformin 500 started",
    ),
    TimelineCandidate(
        candidate_id="c3",
        event_date=date(2026, 3, 19),
        kind=EventKind.VISIT,
        label="Laceration to right foot",
    ),
)


def _event(candidate_id: str, **overrides: object) -> ClinicalEvent:
    base = {
        "event_date": date(2026, 8, 14),
        "kind": EventKind.VISIT,
        "label": "whatever the model said",
        "source": TimelineSource.MODEL_SELECTED,
        "candidate_id": candidate_id,
        "relevance": 0.9,
        "relevance_reason": "same complaint",
    }
    base.update(overrides)
    return ClinicalEvent.model_validate(base)


def _run(draft: TimelineDraft, *, min_relevance: float = 0.3, max_events: int = 12):
    return validated_events(
        draft,
        candidates=CANDIDATES,
        min_relevance=min_relevance,
        max_events=max_events,
    )


class TestAnInventedEventCannotReachAReport:
    def test_an_unknown_candidate_id_is_dropped(self) -> None:
        """It was not selected from the record. It was made up."""
        events, _ = _run(TimelineDraft(events=(_event("c99"),)))
        assert events == ()

    def test_a_missing_candidate_id_is_dropped(self) -> None:
        events, _ = _run(TimelineDraft(events=(_event(""),)))
        assert events == ()

    def test_a_date_that_contradicts_its_candidate_is_dropped(self) -> None:
        """A real event moved to a wrong date is worse than a missing one — a
        physician reads the order as causation."""
        events, _ = _run(
            TimelineDraft(events=(_event("c1", event_date=date(2026, 1, 1)),))
        )
        assert events == ()

    def test_the_label_comes_from_the_candidate_not_the_model(self) -> None:
        """The single line that makes "selects, never authors" a property rather
        than an instruction: a model that rewrites a label into something more
        clinical-sounding has its rewrite discarded."""
        events, _ = _run(
            TimelineDraft(events=(_event("c1", label="Pyrexia of unknown origin"),))
        )
        assert events[0].label == "Fever, five days"

    def test_a_very_long_label_is_cut_rather_than_summarised(self) -> None:
        long_candidate = TimelineCandidate(
            candidate_id="c1",
            event_date=date(2026, 8, 14),
            kind=EventKind.VISIT,
            label=" ".join(f"word{n}" for n in range(30)),
        )
        events, _ = validated_events(
            TimelineDraft(events=(_event("c1"),)),
            candidates=(long_candidate,),
            min_relevance=0.3,
            max_events=12,
        )
        assert len(events[0].label.split()) == 12


class TestRelevance:
    def test_below_the_floor_is_dropped(self) -> None:
        events, _ = _run(TimelineDraft(events=(_event("c1", relevance=0.1),)))
        assert events == ()

    def test_an_unexplained_score_is_dropped(self) -> None:
        """"Related because it is also a knee" is checkable. A bare 0.9 is not."""
        events, _ = _run(TimelineDraft(events=(_event("c1", relevance_reason=None),)))
        assert events == ()

    def test_a_blank_reason_counts_as_none(self) -> None:
        events, _ = _run(TimelineDraft(events=(_event("c1", relevance_reason="   "),)))
        assert events == ()

    def test_the_foot_injury_under_a_fever_complaint_is_dropped(self) -> None:
        """**The case that named the feature.** March's laceration has nothing
        to do with today's fever, and a model that offers it at 0.1 does not get
        to put it on a physician's screen."""
        events, _ = _run(
            TimelineDraft(
                events=(
                    _event("c1", relevance=0.95, relevance_reason="same complaint"),
                    _event(
                        "c3",
                        event_date=date(2026, 3, 19),
                        relevance=0.1,
                        relevance_reason="also a previous visit",
                    ),
                )
            )
        )
        assert [event.candidate_id for event in events] == ["c1"]


class TestTheReportCannotBeLengthenedByAChattyModel:
    def test_over_the_cap_is_truncated(self) -> None:
        events, _ = _run(
            TimelineDraft(
                events=(
                    _event("c1"),
                    _event("c2", event_date=date(2026, 6, 2)),
                    _event("c3", event_date=date(2026, 3, 19)),
                )
            ),
            max_events=2,
        )
        assert len(events) == 2

    def test_one_candidate_returned_twice_renders_once(self) -> None:
        """A model repeating itself must not make one event look like two
        occurrences of the same thing."""
        events, _ = _run(TimelineDraft(events=(_event("c1"), _event("c1"))))
        assert len(events) == 1

    def test_the_omitted_count_is_computed_not_taken_from_the_model(self) -> None:
        """A model that drops an event without saying so would otherwise make
        the report understate the gap — and "3 earlier events are not shown" is
        the line that stops a filtered timeline reading as a complete one."""
        _, omitted = _run(
            TimelineDraft(events=(_event("c1"),), omitted_count=0),
        )
        assert omitted == 2


class TestOrdering:
    def test_newest_first(self) -> None:
        events, _ = _run(
            TimelineDraft(
                events=(
                    _event("c3", event_date=date(2026, 3, 19), relevance_reason="x"),
                    _event("c1", relevance_reason="x"),
                    _event("c2", event_date=date(2026, 6, 2), relevance_reason="x"),
                )
            )
        )
        assert [e.event_date for e in events] == [
            date(2026, 8, 14),
            date(2026, 6, 2),
            date(2026, 3, 19),
        ]

    def test_it_is_stable_under_a_shuffled_input(self) -> None:
        """The report is byte-deterministic and pinned by golden files. An
        unstable sort here would make that a coin-toss."""
        same_day = [
            ClinicalEvent(
                event_date=date(2026, 8, 14),
                kind=EventKind.VISIT,
                label=label,
                candidate_id=cid,
            )
            for label, cid in [("Alpha", "c1"), ("Beta", "c2"), ("Gamma", "c3")]
        ]
        expected = [e.label for e in order_events(list(same_day))]
        for seed in range(10):
            shuffled = list(same_day)
            random.Random(seed).shuffle(shuffled)
            assert [e.label for e in order_events(shuffled)] == expected
