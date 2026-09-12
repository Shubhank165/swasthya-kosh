"""One provider call per intake, not one per report view.

`GET /intakes/{id}/report` rebuilds on every call by design. With a provider
configured and no cache, that is a model call every time a physician reloads the
page — money spent, the request held open while it runs, and the same report
reading differently twice.

The digest is what keeps the cache honest: it covers the candidate set, so a new
document or a newly linked prior visit invalidates the row without anything
having to expire it. A TTL would have the opposite failure — correct-looking
staleness nobody notices.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.clock import FrozenClock
from app.core.ids import SequentialIdFactory
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
from app.domain.timeline.fallback import candidates_from
from app.domain.timeline.model import TimelineDraft, TimelineStatus
from app.repositories.timelines import TimelineRepository, digest_for
from app.services.timeline import TimelineService
from tests.conftest import HOSPITAL_ID

NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)


def _record(intake_id: str, complaint: str, when: datetime = NOW) -> CanonicalRecord:
    return CanonicalRecord(
        intake_id=UUID(intake_id),
        hospital_id=HOSPITAL_ID,
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


TODAY = _record("bbbb1111-0000-4000-8000-000000000009", "fever")
PRIOR = _record(
    "bbbb1111-0000-4000-8000-000000000001",
    "fever",
    datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
)
LATER = _record(
    "bbbb1111-0000-4000-8000-000000000002",
    "fever",
    datetime(2026, 7, 2, 9, 0, tzinfo=UTC),
)


class _CountingProvider:
    """Selects everything, and counts how often it was asked."""

    name = "counting"

    def __init__(self) -> None:
        self.calls = 0

    async def summarise(self, request: Any) -> TimelineDraft:
        self.calls += 1
        from app.domain.timeline.model import ClinicalEvent, TimelineSource

        return TimelineDraft(
            events=tuple(
                ClinicalEvent(
                    event_date=candidate.event_date,
                    kind=candidate.kind,
                    label=candidate.label,
                    source=TimelineSource.MODEL_SELECTED,
                    candidate_id=candidate.candidate_id,
                    relevance=0.9,
                    relevance_reason="same complaint",
                )
                for candidate in request.candidates
            )
        )


def _service(session: Any, provider: Any) -> TimelineService:
    return TimelineService(
        provider=provider,
        clock=FrozenClock(NOW),
        repository=TimelineRepository(session),
        ids=SequentialIdFactory(),
    )


class TestTheProviderIsAskedOnce:
    async def test_a_second_build_reads_the_stored_row(self, session: Any) -> None:
        provider = _CountingProvider()
        service = _service(session, provider)
        first = await service.build(TODAY, prior=[PRIOR])
        second = await service.build(TODAY, prior=[PRIOR])
        assert provider.calls == 1
        assert first.events == second.events
        assert second.status is TimelineStatus.FILTERED

    async def test_a_new_prior_visit_invalidates_it(self, session: Any) -> None:
        """The digest covers the candidates, so nothing has to expire a row."""
        provider = _CountingProvider()
        service = _service(session, provider)
        await service.build(TODAY, prior=[PRIOR])
        await service.build(TODAY, prior=[PRIOR, LATER])
        assert provider.calls == 2

    async def test_two_languages_are_two_rows(self, session: Any) -> None:
        """A Hindi and an English report are different documents even when the
        selection is identical: the labels differ."""
        provider = _CountingProvider()
        service = _service(session, provider)
        await service.build(TODAY, prior=[PRIOR], language="en")
        await service.build(TODAY, prior=[PRIOR], language="hi")
        assert provider.calls == 2


class TestWithNoProvider:
    async def test_nothing_is_cached(self, session: Any) -> None:
        """Pure code is cheap and gives the same answer every time. A row and a
        failure mode to save a list comprehension is a bad trade."""
        service = _service(session, None)
        snapshot = await service.build(TODAY, prior=[PRIOR])
        assert snapshot.status is TimelineStatus.UNFILTERED
        stored = await TimelineRepository(session).get(
            hospital_id=HOSPITAL_ID,
            intake_id=str(TODAY.intake_id),
            language="en",
        )
        assert stored is None


class TestTheDigest:
    def test_it_does_not_depend_on_candidate_order(self) -> None:
        """A cache that misses at random would fire a model call on a reload."""
        candidates = candidates_from([PRIOR, LATER])
        reversed_first = candidates_from([LATER, PRIOR])
        assert digest_for(candidates) == digest_for(reversed_first)

    def test_a_changed_record_changes_it(self) -> None:
        assert digest_for(candidates_from([PRIOR])) != digest_for(
            candidates_from([PRIOR, LATER])
        )
