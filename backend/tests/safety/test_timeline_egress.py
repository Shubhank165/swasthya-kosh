"""What a timeline request may and may not carry out of the building.

Today Vertex sees a photograph of a prescription the patient handed over ten
minutes ago. The timeline provider would additionally see coded values from
earlier visits, and the names of medicines they were on — a longitudinal picture
rather than one document. That is a materially larger category of egress, and it
belongs in the same DPIA conversation as the Jetson handwriting path.

`TIMELINE_SHARE_PRIOR_RECORDS` is the policy. **This file is the control.** A
flag nobody tests is a comment.

The PHI markers are the ones `test_logging_phi.py` already enumerates, because
the thing that must not leave in a log is the thing that must not leave in a
request.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from app.adapters.timeline.vertex import (
    PriorRecordEgressRefused,
    VertexTimelineProvider,
)
from app.core.config import Settings
from app.domain.timeline.model import (
    EventKind,
    TimelineCandidate,
    TimelineRequest,
)
from tests.safety.test_logging_phi import CLINICAL_TEXT


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "timeline_provider": "vertex",
        "timeline_model_id": "gemini-2.5-flash",
        "vertex_project": "medikiosk-test",
        "vertex_region": "asia-south1",
        "vertex_zdr_enabled": True,
    }
    base.update(overrides)
    return Settings(**base)


PRIOR_VISIT = TimelineCandidate(
    candidate_id="c1",
    event_date=date(2026, 6, 2),
    kind=EventKind.VISIT,
    label="Joint pain",
    intake_id="3f1c2a10-0000-4000-8000-000000000001",
)

OWN_DOCUMENT = TimelineCandidate(
    candidate_id="c2",
    event_date=date(2026, 8, 14),
    kind=EventKind.MEDICATION,
    label="Metformin",
    document_id="doc_000001",
)


class TestTheProviderRefusesToConstructWithoutResidencyAndZDR:
    def test_a_non_indian_region_is_refused(self) -> None:
        from app.adapters.timeline.vertex import ProviderNotConfigured

        with pytest.raises(ProviderNotConfigured):
            VertexTimelineProvider(_settings(vertex_region="us-central1"))

    def test_zdr_must_be_asserted(self) -> None:
        from app.adapters.timeline.vertex import ProviderNotConfigured

        with pytest.raises(ProviderNotConfigured):
            VertexTimelineProvider(_settings(vertex_zdr_enabled=False))

    def test_the_model_id_is_configuration_never_a_literal(self) -> None:
        from app.adapters.timeline.vertex import ProviderNotConfigured

        with pytest.raises(ProviderNotConfigured):
            VertexTimelineProvider(_settings(timeline_model_id=None))


class TestTheEgressFlag:
    async def test_prior_intake_candidates_are_refused_when_sharing_is_off(self) -> None:
        """Off is the default. A caller that built candidates from prior visits
        anyway has a bug, and raising beats filtering silently: a deployment
        that thinks it is getting relevance filtering over five visits and is
        quietly getting it over one has been misled about what the physician is
        reading."""
        provider = VertexTimelineProvider(_settings(timeline_share_prior_records=False))
        with pytest.raises(PriorRecordEgressRefused):
            await provider.summarise(
                TimelineRequest(today={"chief_complaint": "fever"}, candidates=(PRIOR_VISIT,))
            )

    async def test_the_intakes_own_documents_still_go(self) -> None:
        """With the flag off the provider still runs, seeing only this intake's
        own documents and today's answers — strictly less than the OCR path
        already sends. That is a shippable middle setting rather than
        all-or-nothing, which is why the flag guards the candidates and not the
        provider."""
        provider = VertexTimelineProvider(_settings(timeline_share_prior_records=False))
        # No network: an empty candidate set returns before the client is built.
        request = TimelineRequest(today={"chief_complaint": "fever"}, candidates=())
        assert await provider.summarise(request) is None

        # And a document-only candidate set is not refused.
        provider._client = _StubClient()
        result = await provider.summarise(
            TimelineRequest(today={"chief_complaint": "fever"}, candidates=(OWN_DOCUMENT,))
        )
        assert result is not None

    async def test_prior_candidates_are_accepted_once_sharing_is_on(self) -> None:
        provider = VertexTimelineProvider(_settings(timeline_share_prior_records=True))
        provider._client = _StubClient()
        result = await provider.summarise(
            TimelineRequest(today={"chief_complaint": "fever"}, candidates=(PRIOR_VISIT,))
        )
        assert result is not None


class TestTheRequestCarriesNoPHI:
    def test_no_phi_marker_survives_serialisation(self) -> None:
        """The same strings `test_logging_phi.py` forbids in a log line. What
        must not reach a log must not reach a model."""
        request = TimelineRequest(
            today={"chief_complaint": "fever", "department": "kayachikitsa"},
            candidates=(PRIOR_VISIT, OWN_DOCUMENT),
        )
        serialised = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
        for marker in CLINICAL_TEXT:
            assert marker not in serialised

    def test_candidate_ids_are_opaque_and_short(self) -> None:
        """`c1`, not a uuid: nothing identifying travels in an id, and a model
        returns something a human can check against the list it was given."""
        request = TimelineRequest(candidates=(PRIOR_VISIT, OWN_DOCUMENT))
        assert [c.candidate_id for c in request.candidates] == ["c1", "c2"]


class _StubClient:
    """Stands in for the genai client. Makes no network call."""

    def __init__(self) -> None:
        self.aio = self

    @property
    def models(self) -> Any:
        return self

    async def generate_content(self, **_: Any) -> Any:
        class _Response:
            text = json.dumps({"events": [], "omitted_count": 0})

        return _Response()
