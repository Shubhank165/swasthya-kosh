"""Building a patient's dated history — the problem statement's timeline.

Three stages, and **the deterministic ones carry the guarantee**:

1. **Pre-filter, pure.** Prior records are capped, sorted and given stable short
   candidate ids (`c1..cN`), so a provider returns something short and checkable
   and nothing identifying travels in an id.
2. **Model, optional.** Scores relevance against today's complaint and returns a
   subset. Off by default.
3. **Post-filter, pure.** `validate.py` drops unknown ids, contradicted dates and
   below-floor scores, then truncates and sorts.

The model proposes; pure code disposes. A chatty model cannot lengthen the
report, a hallucinated event cannot reach a physician, and with the model off
stage 1 alone still yields a dated timeline — which is the requirement met.

**Today's complaint is not free text and does not come from a model.**
`_today_context` reads the coded `chief_complaint` value — the same field
`identity.py` already reads — plus today's answered voice facts and the
department code. Today's red-flag free text and anything in `ingest_raw` stay
out: a red flag's wording is a device's phrasing of an emergency, not a
description of a complaint, and raw payloads have not been through redaction.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.adapters.protocols import TimelineProvider
from app.core.clock import Clock
from app.core.ids import IdFactory
from app.core.logging import get_logger
from app.domain.clinical.enums import Section
from app.domain.documents.extraction import DocumentExtraction
from app.domain.record import CanonicalRecord, FieldStatus
from app.domain.timeline.fallback import candidates_from, deterministic_timeline
from app.domain.timeline.model import (
    TimelineRequest,
    TimelineSnapshot,
    TimelineStatus,
)
from app.domain.timeline.validate import validated_events
from app.repositories.timelines import TimelineRepository, digest_for, snapshot_from

logger = get_logger(__name__)

#: Bumped when the selection instruction changes, so a cached timeline built
#: under an older prompt is attributable in a stored row.
PROMPT_VERSION = "1.0"

#: Sections whose answered facts describe what the patient came in with today.
_TODAY_SECTIONS = frozenset(
    {Section.CHIEF_COMPLAINT, Section.HPI, Section.RED_FLAG_SCREEN}
)


def _today_context(record: CanonicalRecord) -> dict[str, str]:
    """What the patient came in with, as coded values only.

    Coded values, never the patient's own words. Those are theirs, they are
    already on the report verbatim, and sending a sentence a patient said to a
    model in order to decide which old visits to show is a much larger claim on
    their words than this feature needs to make.
    """
    today: dict[str, str] = {}
    if record.department_code:
        today["department"] = record.department_code
    for fact in record.live_facts():
        if fact.status is not FieldStatus.ANSWERED:
            continue
        if fact.section not in _TODAY_SECTIONS:
            continue
        rendered = fact.rendered_value()
        if rendered:
            today[fact.field_id] = str(rendered)
    return today


class TimelineService:
    """Builds the timeline for one intake, with or without a provider."""

    def __init__(
        self,
        *,
        provider: TimelineProvider | None,
        clock: Clock,
        repository: TimelineRepository | None = None,
        ids: IdFactory | None = None,
        model_id: str | None = None,
        max_events: int = 12,
        min_relevance: float = 0.3,
    ) -> None:
        self._provider = provider
        self._clock = clock
        self._repository = repository
        self._ids = ids
        self._model_id = model_id
        self._max_events = max_events
        self._min_relevance = min_relevance

    async def build(
        self,
        record: CanonicalRecord,
        *,
        prior: Sequence[CanonicalRecord],
        extractions: Sequence[DocumentExtraction] = (),
        language: str | None = None,
    ) -> TimelineSnapshot:
        """The timeline as it should be rendered for this intake."""
        fallback = deterministic_timeline(
            prior, extractions, max_events=self._max_events
        )
        if self._provider is None:
            # Pure code, cheap, and the same answer every time. Caching it would
            # add a row and a failure mode to save a list comprehension.
            return fallback

        candidates = candidates_from(prior, extractions)
        if not candidates:
            return fallback

        # `GET /intakes/{id}/report` rebuilds on every call by design. Without
        # this the provider would fire once per *view*, with the physician
        # holding the request open, and the same report would read differently
        # on a reload. The digest covers the candidates, so a new document or a
        # newly linked visit invalidates the row without anything expiring it.
        digest = digest_for(candidates)
        report_language = language or record.language
        cached = await self._cached(record, report_language, digest)
        if cached is not None:
            return cached

        request = TimelineRequest(
            today=_today_context(record),
            candidates=candidates,
            language=record.language,
            max_events=self._max_events,
        )
        draft = await self._provider.summarise(request)
        if draft is None:
            # A normal outcome. The fallback is a complete dated history rather
            # than a degraded one, so an unavailable provider costs relevance
            # filtering and not the feature.
            return fallback

        events, omitted = validated_events(
            draft,
            candidates=candidates,
            min_relevance=self._min_relevance,
            max_events=self._max_events,
        )
        if not events:
            # Everything the model offered was dropped. Falling back to the full
            # history is the honest answer: "nothing relevant" and "the model's
            # answers did not survive the gate" are different states, and only
            # one of them is something to show a physician as a finding.
            logger.info("timeline_draft_empty_after_validation", provider=self._provider.name)
            return fallback

        snapshot = TimelineSnapshot(
            status=TimelineStatus.FILTERED,
            events=events,
            omitted_count=omitted,
            provider=self._provider.name,
            model_id=self._model_id,
            generated_at=self._clock.now(),
        )
        await self._store(record, report_language, digest, snapshot)
        return snapshot

    async def _cached(
        self, record: CanonicalRecord, language: str, digest: str
    ) -> TimelineSnapshot | None:
        if self._repository is None:
            return None
        row = await self._repository.get(
            hospital_id=record.hospital_id,
            intake_id=str(record.intake_id),
            language=language,
        )
        if row is None or row.input_digest != digest:
            return None
        return snapshot_from(row)

    async def _store(
        self,
        record: CanonicalRecord,
        language: str,
        digest: str,
        snapshot: TimelineSnapshot,
    ) -> None:
        if self._repository is None or self._ids is None:
            return
        await self._repository.upsert(
            timeline_id=self._ids.new_id("timeline"),
            hospital_id=record.hospital_id,
            intake_id=str(record.intake_id),
            language=language,
            snapshot=snapshot,
            input_digest=digest,
            model_id=self._model_id,
            prompt_version=PROMPT_VERSION,
            generated_at=snapshot.generated_at or self._clock.now(),
        )
