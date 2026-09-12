"""Built timelines, cached per intake and language.

The cache exists to bound one cost and hold one property. The cost is a model
call per *report view* rather than per intake — `GET /intakes/{id}/report`
rebuilds on every call by design, and a physician reloading a page should not
spend money. The property is that two readers opening the same report see the
same timeline.

`input_digest` is what keeps it honest. It hashes the candidates the timeline was
built from, so a newly uploaded document or a newly linked prior visit changes
the digest and the stored row simply stops matching. Nothing has to remember to
expire anything, which is the failure mode a cache with a TTL would have.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.timeline.model import (
    ClinicalEvent,
    TimelineCandidate,
    TimelineSnapshot,
    TimelineStatus,
)
from app.models.clinical import ClinicalTimeline


def digest_for(candidates: tuple[TimelineCandidate, ...]) -> str:
    """A stable hash of what a timeline was built from.

    Sorted and serialised with sorted keys, so the digest depends on the
    candidate set and not on dict ordering — otherwise a cache would miss at
    random and a model call would fire on a page reload.
    """
    payload = sorted(
        json.dumps(candidate.model_dump(mode="json"), sort_keys=True)
        for candidate in candidates
    )
    return hashlib.sha256("\n".join(payload).encode("utf-8")).hexdigest()


class TimelineRepository:
    """Reads and writes `clinical_timelines`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, *, hospital_id: str, intake_id: str, language: str
    ) -> ClinicalTimeline | None:
        result = await self._session.execute(
            select(ClinicalTimeline).where(
                ClinicalTimeline.hospital_id == hospital_id,
                ClinicalTimeline.intake_id == intake_id,
                ClinicalTimeline.language == language,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        timeline_id: str,
        hospital_id: str,
        intake_id: str,
        language: str,
        snapshot: TimelineSnapshot,
        input_digest: str,
        model_id: str | None,
        prompt_version: str | None,
        generated_at: datetime,
    ) -> ClinicalTimeline:
        row = await self.get(
            hospital_id=hospital_id, intake_id=intake_id, language=language
        )
        events = [event.model_dump(mode="json") for event in snapshot.events]
        if row is None:
            row = ClinicalTimeline(
                id=timeline_id,
                hospital_id=hospital_id,
                intake_id=intake_id,
                language=language,
            )
            self._session.add(row)
        row.status = snapshot.status.value
        row.provider = snapshot.provider
        row.model_id = model_id
        row.prompt_version = prompt_version
        row.input_digest = input_digest
        row.events = events
        row.omitted_count = snapshot.omitted_count
        row.generated_at = generated_at
        await self._session.flush()
        return row


def snapshot_from(row: ClinicalTimeline) -> TimelineSnapshot:
    """A stored row back as the value the report builder takes."""
    return TimelineSnapshot(
        status=TimelineStatus(row.status),
        events=tuple(ClinicalEvent.model_validate(event) for event in row.events),
        omitted_count=row.omitted_count,
        provider=row.provider,
        model_id=row.model_id,
        generated_at=row.generated_at,
    )
