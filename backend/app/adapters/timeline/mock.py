"""A fixture-backed timeline provider. No cloud, no cost, no network.

Keyed by **scenario name**, not by a digest of the request. A digest-keyed
fixture invalidates the moment anything about serialisation changes — a field
added, a key reordered — and the failure looks like "the mock stopped working"
rather than "the fixture is stale", which is a morning lost. The OCR mock was
keyed by digest and this is the lesson from it.

With no fixture matching, it falls back to a rule a human can read: the
candidates that share a tag with today's complaint score high, the rest score
below the floor and are dropped by `validate.py` like any other. That is enough
to exercise the whole relevance path end to end — including the foot injury
under a fever complaint — without a model anywhere in the test suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.domain.timeline.model import (
    ClinicalEvent,
    TimelineCandidate,
    TimelineDraft,
    TimelineRequest,
    TimelineSource,
)

logger = get_logger(__name__)


class MockTimelineProvider:
    """Deterministic selection. Visibly a mock."""

    name = "mock"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = Path(fixtures_dir) if fixtures_dir else None

    async def summarise(self, request: TimelineRequest) -> TimelineDraft | None:
        scenario = request.today.get("scenario")
        if scenario and self._fixtures_dir is not None:
            loaded = self._from_fixture(scenario)
            if loaded is not None:
                return loaded
        return self._by_overlap(request)

    def _from_fixture(self, scenario: str) -> TimelineDraft | None:
        path = self._fixtures_dir / f"{scenario}.json" if self._fixtures_dir else None
        if path is None or not path.is_file():
            return None
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            logger.info("timeline_fixture_unreadable", scenario=scenario)
            return None
        return TimelineDraft.model_validate(raw)

    def _by_overlap(self, request: TimelineRequest) -> TimelineDraft:
        """Share a coded tag with today, or you are not related to it.

        Crude on purpose. A cleverer rule here would make the mock's judgement
        the thing under test, when what the tests need to exercise is the
        *gate* — and the gate does not care how a score was arrived at.
        """
        today = {value for key, value in request.today.items() if key != "scenario"}
        events: list[ClinicalEvent] = []
        omitted = 0
        for candidate in request.candidates:
            shared = _shared(candidate, today)
            if shared is None:
                omitted += 1
                continue
            events.append(
                ClinicalEvent(
                    event_date=candidate.event_date,
                    kind=candidate.kind,
                    label=candidate.label,
                    source=TimelineSource.MODEL_SELECTED,
                    intake_id=candidate.intake_id,
                    document_id=candidate.document_id,
                    candidate_id=candidate.candidate_id,
                    relevance=0.9,
                    relevance_reason=f"shares {shared} with today's complaint",
                )
            )
        return TimelineDraft(events=tuple(events), omitted_count=omitted)


def _shared(candidate: TimelineCandidate, today: set[str]) -> str | None:
    for tag in candidate.tags:
        _, _, value = tag.partition("=")
        if value and value in today:
            return value
    for value in today:
        if value and value.lower() in candidate.label.lower():
            return value
    return None
