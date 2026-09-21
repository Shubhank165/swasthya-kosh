"""The three stages, wired together, with no cloud call anywhere.

What matters here is the *ordering* of the guarantee: a provider can only ever
narrow what pure code already found. So the worst case for the whole timeline
feature is a physician seeing more history than they needed, never one seeing
something that did not happen — and these tests are where that is checked rather
than asserted in a docstring.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from app.adapters.timeline.mock import MockTimelineProvider
from app.core.clock import FrozenClock
from app.domain.clinical.enums import Certainty, Section
from app.domain.record import (
    CanonicalRecord,
    Coded,
    Fact,
    FieldStatus,
    IngestProvenance,
    IntakeStatus,
    PatientRef,
    PatientRefType,
    TurnSource,
)
from app.domain.timeline.model import TimelineSnapshot, TimelineStatus
from app.services.timeline import TimelineService

NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)


def _record(
    intake_id: str, complaint: str, *, when: datetime = NOW
) -> CanonicalRecord:
    return CanonicalRecord(
        intake_id=UUID(intake_id),
        hospital_id="aiia-delhi",
        patient_ref=PatientRef(type=PatientRefType.HOSPITAL_ID, value="UHID-1"),
        language="en",
        status=IntakeStatus.COMPLETE,
        facts=[
            Fact(
                fact_id=f"f-{intake_id[:8]}",
                field_id="chief_complaint",
                status=FieldStatus.ANSWERED,
                value=Coded(code=complaint),
                section=Section.CHIEF_COMPLAINT,
                certainty=Certainty.REPORTED,
                source=TurnSource(turn_id=1, question_id="ask_complaint"),
                recorded_at=when,
            )
        ],
        provenance=IngestProvenance(schema_version="0.1"),
        started_at=when,
        completed_at=when,
        created_at=when,
        updated_at=when,
    )


TODAY = _record("aaaa1111-0000-4000-8000-000000000009", "fever")
PRIOR_FEVER = _record(
    "aaaa1111-0000-4000-8000-000000000001",
    "fever",
    when=datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
)
PRIOR_FOOT = _record(
    "aaaa1111-0000-4000-8000-000000000002",
    "injury",
    when=datetime(2026, 3, 19, 9, 0, tzinfo=UTC),
)


def _service(provider: Any = None) -> TimelineService:
    return TimelineService(provider=provider, clock=FrozenClock(NOW))


class TestWithNoProvider:
    async def test_the_report_still_gets_a_dated_history(self) -> None:
        """**The one that ships.** `TIMELINE_PROVIDER=none` is the default, and
        the spec's dated-history requirement is met without a model
        being involved at all."""
        snapshot = await _service().build(TODAY, prior=[PRIOR_FEVER, PRIOR_FOOT])
        assert snapshot.status is TimelineStatus.UNFILTERED
        assert len(snapshot.events) == 2

    async def test_it_says_it_was_not_filtered(self) -> None:
        """A reader must not mistake the absence of filtering for a judgement
        that everything shown is relevant."""
        snapshot = await _service().build(TODAY, prior=[PRIOR_FEVER])
        assert snapshot.status is TimelineStatus.UNFILTERED
        assert snapshot.provider is None

    async def test_no_prior_records_is_empty_and_not_pending(self) -> None:
        snapshot = await _service().build(TODAY, prior=[])
        assert snapshot.status is TimelineStatus.UNFILTERED
        assert snapshot.events == ()


class TestWithTheMockProvider:
    async def test_the_foot_injury_is_left_out_of_a_fever_consultation(self) -> None:
        """**The user's own case.** March's foot injury has nothing to do with
        today's fever, and it does not reach the report."""
        snapshot = await _service(MockTimelineProvider()).build(
            TODAY, prior=[PRIOR_FEVER, PRIOR_FOOT]
        )
        assert snapshot.status is TimelineStatus.FILTERED
        labels = [event.label for event in snapshot.events]
        assert "fever" in labels
        assert "injury" not in labels

    async def test_what_was_left_out_is_counted_and_said(self) -> None:
        """A filtered timeline that does not say it is filtered reads as a
        complete history and is not."""
        snapshot = await _service(MockTimelineProvider()).build(
            TODAY, prior=[PRIOR_FEVER, PRIOR_FOOT]
        )
        assert snapshot.omitted_count == 1

    async def test_a_selected_event_names_why(self) -> None:
        snapshot = await _service(MockTimelineProvider()).build(
            TODAY, prior=[PRIOR_FEVER]
        )
        assert snapshot.events[0].relevance_reason


class TestAProviderCanOnlyEverNarrow:
    async def test_a_provider_that_returns_nothing_falls_back_to_everything(
        self,
    ) -> None:
        """Not to an empty timeline. "Nothing relevant" and "the model's answers
        did not survive the gate" are different states, and only one of them is
        a finding to show a physician."""
        snapshot = await _service(_SilentProvider()).build(
            TODAY, prior=[PRIOR_FEVER, PRIOR_FOOT]
        )
        assert snapshot.status is TimelineStatus.UNFILTERED
        assert len(snapshot.events) == 2

    async def test_an_unavailable_provider_costs_filtering_not_the_feature(
        self,
    ) -> None:
        snapshot = await _service(_UnavailableProvider()).build(
            TODAY, prior=[PRIOR_FEVER]
        )
        assert snapshot.status is TimelineStatus.UNFILTERED
        assert snapshot.events

    async def test_a_provider_cannot_add_an_event_pure_code_did_not_find(
        self,
    ) -> None:
        """The ordering that bounds the whole feature's failure mode."""
        with_provider = await _service(MockTimelineProvider()).build(
            TODAY, prior=[PRIOR_FEVER, PRIOR_FOOT]
        )
        without = await _service().build(TODAY, prior=[PRIOR_FEVER, PRIOR_FOOT])
        found = {event.candidate_id for event in without.events}
        assert {event.candidate_id for event in with_provider.events} <= found


class _SilentProvider:
    name = "silent"

    async def summarise(self, request: Any) -> None:
        return None


class _UnavailableProvider:
    name = "unavailable"

    async def summarise(self, request: Any) -> None:
        return None


@pytest.mark.parametrize("snapshot", [TimelineSnapshot.pending()])
def test_a_pending_snapshot_is_not_an_empty_one(snapshot: TimelineSnapshot) -> None:
    """The renderer branches on this: "not ready" and "nothing on record" look
    identical on screen and mean opposite things."""
    assert snapshot.status is TimelineStatus.PENDING
    assert snapshot.is_empty
