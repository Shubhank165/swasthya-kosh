"""Vertex timeline selection.

**This is the only place prior consultation content can leave the building**, and
that is a different category of egress from everything before it. Today Vertex
sees a photograph of a prescription the patient handed over ten minutes ago. This
would additionally send coded values from earlier visits, the patient's own words
as they were recorded then, and the names of medicines they were on — a
longitudinal picture rather than a single document.

So `TIMELINE_SHARE_PRIOR_RECORDS` defaults false, and with it false this provider
**still runs**: it sees this intake's own documents and today's answers, which is
strictly less than the OCR path already sends. That is a shippable middle
setting rather than an all-or-nothing switch, and it is why the flag guards the
*candidates* rather than the provider.

The region and ZDR guards are copied from `adapters/ocr/gemini.py` deliberately
rather than shared: a guard that lives in one place and is imported is a guard
somebody can forget to import.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings
from app.core.errors import MediKioskError
from app.core.logging import get_logger
from app.domain.timeline.model import TimelineDraft, TimelineRequest

logger = get_logger(__name__)


class ProviderNotConfigured(MediKioskError):
    """The provider cannot run with the configuration it was given."""

    status_code = 503
    code = "provider_not_configured"


class PriorRecordEgressRefused(MediKioskError):
    """Prior consultation content was offered while sharing it is switched off.

    A bug, not a user error: something built candidates from prior intakes on a
    deployment configured not to send them. Raising beats filtering silently —
    a caller that thinks it is getting relevance filtering over five visits and
    is quietly getting it over one has been misled about what the physician is
    reading.
    """

    status_code = 500
    code = "timeline_egress_refused"


#: Select, never author. Shaped like `EXTRACTION_INSTRUCTION` in the OCR adapter.
SELECTION_INSTRUCTION = """\
You are given a patient's earlier records as a list of candidates, and a short
description of what they have come in with today.

Select the candidates that relate to today's complaint. You are selecting, not
writing.

Rules, all of them absolute:
- Every event you return MUST reproduce a candidate_id from the list given, and
  MUST reproduce that candidate's date exactly. Do not adjust a date.
- Do not state a diagnosis, an impression, a cause, a prognosis or any advice.
- The label must be at most 12 words, copied from the candidate or shortened by
  deleting words from it. Do not rephrase it into clinical language.
- Every event needs a relevance_reason naming the shared element: the same
  complaint, the same body system, the same medicine, the same investigation.
  If you cannot name one, omit the event.
- Omit rather than pad. Returning three related events is a better answer than
  returning eight of which five are unrelated.

Return JSON: {"events": [{"candidate_id", "event_date", "kind", "label",
"relevance", "relevance_reason"}], "omitted_count": n}
"""


class VertexTimelineProvider:
    """Gemini on Vertex, in an Indian region, with ZDR asserted."""

    name = "vertex"

    #: Regions where Vertex serves models inside India.
    INDIAN_REGIONS: frozenset[str] = frozenset({"asia-south1", "asia-south2"})

    def __init__(self, settings: Settings) -> None:
        if not settings.timeline_model_id:
            raise ProviderNotConfigured(
                "TIMELINE_MODEL_ID is not set; the model is configuration, never a literal"
            )
        if not settings.vertex_project:
            raise ProviderNotConfigured("VERTEX_PROJECT is not set")
        if settings.vertex_region not in self.INDIAN_REGIONS:
            raise ProviderNotConfigured(
                f"VERTEX_REGION is '{settings.vertex_region}', which is not an Indian "
                f"region. Serving this model from outside India is a decision for the "
                f"team, not for the service — see docs/DECISIONS.md. "
                f"Indian regions: {sorted(self.INDIAN_REGIONS)}"
            )
        if not settings.vertex_zdr_enabled:
            raise ProviderNotConfigured(
                "VERTEX_ZDR_ENABLED is false. Zero Data Retention must be confirmed on "
                "the project before a patient's records are sent to a model."
            )
        self._settings = settings
        self._model_id = settings.timeline_model_id
        self._share_prior = settings.timeline_share_prior_records
        self._client: Any | None = None

    async def summarise(self, request: TimelineRequest) -> TimelineDraft | None:
        if not self._share_prior and any(
            candidate.intake_id is not None for candidate in request.candidates
        ):
            raise PriorRecordEgressRefused(
                "TIMELINE_SHARE_PRIOR_RECORDS is false, but candidates drawn from "
                "prior intakes were offered. Prior consultation content is a "
                "larger category of egress than an uploaded document and needs a "
                "deliberate decision — see docs/DECISIONS.md."
            )
        if not request.candidates:
            return None

        client = self._get_client()
        payload = request.model_dump(mode="json")
        try:
            response = await client.aio.models.generate_content(
                model=self._model_id,
                contents=[SELECTION_INSTRUCTION, json.dumps(payload, ensure_ascii=False)],
                config={"response_mime_type": "application/json"},
            )
        except Exception as exc:  # pragma: no cover - network path
            # `None` is a normal outcome. The caller falls back to the
            # deterministic timeline, which is a complete dated history rather
            # than a degraded one, so an outage costs relevance filtering and
            # not the feature.
            logger.warning("timeline_provider_failed", error=type(exc).__name__)
            return None

        text = getattr(response, "text", None)
        if not text:
            return None
        try:
            return TimelineDraft.model_validate(json.loads(text))
        except (ValueError, TypeError):
            # Malformed output is not repaired and not partially salvaged.
            # `validate.py` would drop most of it anyway, and a half-parsed
            # draft is a draft nobody can reason about.
            logger.warning("timeline_provider_unparseable")
            return None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:  # pragma: no cover
                raise ProviderNotConfigured(
                    "google-genai is not installed; TIMELINE_PROVIDER=vertex needs it"
                ) from exc
            self._client = genai.Client(
                vertexai=True,
                project=self._settings.vertex_project,
                location=self._settings.vertex_region,
            )
        return self._client
