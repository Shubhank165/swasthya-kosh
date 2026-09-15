"""Vertex AI repair provider.

**The only language model call anywhere near clinical data**, and it is
restricted to one job: taking a payload that failed its contract and
restructuring it into the schema. It does not extract, does not infer and does
not write prose.

The instruction below is the whole safety argument. It says three things the
model must not do — invent, infer, or resolve — and one thing it must:
mark anything absent as `unresolved`. Structured output enforces the schema, and
the caller re-validates the result against the contract regardless of what the
model claims, because an instruction is not a guarantee.

Same residency preconditions as the OCR provider, and the same refusal to
construct without them. Excluded from coverage; the mock is what CI runs.
"""

from __future__ import annotations

import json
from typing import Any

from app.adapters.ocr.gemini import ProviderNotConfigured
from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

REPAIR_INSTRUCTION = """\
You are given a JSON payload from a clinical intake kiosk that failed schema
validation, and the schema it must satisfy.

Restructure the payload so it validates. That is your entire task.

You MUST NOT:
- invent a value, a field, a turn or a red flag that is not in the input;
- infer a value that is not literally present, however obvious it seems;
- resolve an ambiguity — "maybe two weeks" stays "maybe two weeks";
- change a field's status to a stronger one;
- add any clinical interpretation, diagnosis or advice.

You MUST:
- mark any field whose answer is absent, empty or unreadable as "unresolved";
- keep every original text string exactly as it appears, in its original script;
- keep every field that exists, even one you do not recognise.

If a field cannot be restructured without inventing something, mark it
"unresolved" and move on. An unresolved field is a correct answer. A guessed one
is a clinical error.
"""


class VertexRepairProvider:
    """Structured-output repair on Vertex AI."""

    name = "vertex"

    INDIAN_REGIONS: frozenset[str] = frozenset({"asia-south1", "asia-south2"})

    def __init__(self, settings: Settings) -> None:
        if not settings.repair_model_id:
            raise ProviderNotConfigured("REPAIR_MODEL_ID is not set")
        if not settings.vertex_project:
            raise ProviderNotConfigured("VERTEX_PROJECT is not set")
        if settings.vertex_region not in self.INDIAN_REGIONS:
            raise ProviderNotConfigured(
                f"VERTEX_REGION is '{settings.vertex_region}', which is not an Indian "
                "region — see docs/DECISIONS.md"
            )
        if not settings.vertex_zdr_enabled:
            raise ProviderNotConfigured(
                "VERTEX_ZDR_ENABLED is false; a patient's answers are not sent to a "
                "model that may retain them"
            )
        self._settings = settings
        self._model_id = settings.repair_model_id
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:  # pragma: no cover
                raise ProviderNotConfigured(
                    "google-genai is not installed; install the 'gcp' extra"
                ) from exc
            self._client = genai.Client(
                vertexai=True,
                project=self._settings.vertex_project,
                location=self._settings.vertex_region,
            )
        return self._client

    async def repair(
        self, payload: dict[str, Any], *, schema: dict[str, Any], errors: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        from google.genai import types

        client = self._get_client()
        prompt = (
            f"{REPAIR_INSTRUCTION}\n\n"
            f"Validation errors:\n{json.dumps(errors, ensure_ascii=False, indent=2)}\n\n"
            f"Payload:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        try:
            response = await client.aio.models.generate_content(
                model=self._model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0.0,
                ),
            )
            result: dict[str, Any] = json.loads(response.text)
        except Exception:
            # A failed repair is not an error the caller has to handle
            # specially — it is one of the two expected outcomes, and the
            # payload is stored raw either way.
            logger.warning("repair_call_failed", provider=self.name)
            return None
        return result


PREFILL_INSTRUCTION = """\
You are given a patient's own free-text description of their complaint from a
clinical intake kiosk, and a list of upcoming structured questions the kiosk
has not yet asked.

For each question, decide whether the free text already answers it clearly
enough to suggest a value. The patient will see any suggestion you make as a
pre-filled option or figure on a screen they have not reached yet, and must
actively confirm or correct it — nothing you return is recorded on its own.

You MUST NOT:
- invent a value the free text does not support, however plausible it seems;
- guess at a value the text only hints at or leaves ambiguous;
- suggest a choice option that is not literally one of the option codes given
  for that question;
- suggest a number outside the range the question gives, if one is given;
- add any clinical interpretation, diagnosis or advice.

You MUST:
- omit entirely any question the free text does not clearly answer;
- use only the option codes given for a choice question, never a synonym, a
  translation, or a label instead of its code;
- state numbers exactly as the patient stated them, with no rounding and no
  unit conversion.

`kind` is not yours to choose — it is fixed by the question's `answer_type`,
and a mismatch is discarded by the caller without being shown to anyone:

    single_choice   -> "coded"       value = one option code
    multi_choice    -> "coded_list"  codes = a list of option codes
    yes_no_unknown  -> "bool"        value = "true" or "false"
    number          -> "number"      value = the figure
    scale           -> "scale"       value = the figure
    duration        -> "duration"    value = the figure, unit = one of
                                     hour | day | week | month | year

`unit` is always singular. "4 days" is value "4" with unit "day", never
"days", and never kind "number" because it happens to carry a figure.

Return an entry only for a question you are confident about. An omitted
question is a correct answer. A guessed one is a clinical error.
"""

#: The structured-output schema. Every suggestion returns as a string so the
#: schema stays uniform across answer types; `app/services/prefill.py` parses
#: and validates each one against the very question it claims to answer, so
#: nothing here is trusted for its type either, only for its shape.
PREFILL_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field_id": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["bool", "number", "scale", "coded", "coded_list", "duration"],
                    },
                    "value": {"type": "string"},
                    "codes": {"type": "array", "items": {"type": "string"}},
                    "unit": {"type": "string"},
                },
                "required": ["field_id", "kind"],
            },
        },
    },
    "required": ["suggestions"],
}


class VertexPrefillProvider:
    """Structured-output prefill suggestions on Vertex AI.

    Same residency preconditions as the repair and OCR providers, and the same
    refusal to construct without them. Excluded from coverage; the mock is what
    CI runs.
    """

    name = "vertex"

    INDIAN_REGIONS: frozenset[str] = frozenset({"asia-south1", "asia-south2"})

    def __init__(self, settings: Settings) -> None:
        if not settings.prefill_model_id:
            raise ProviderNotConfigured("PREFILL_MODEL_ID is not set")
        if not settings.vertex_project:
            raise ProviderNotConfigured("VERTEX_PROJECT is not set")
        if settings.vertex_region not in self.INDIAN_REGIONS:
            raise ProviderNotConfigured(
                f"VERTEX_REGION is '{settings.vertex_region}', which is not an Indian "
                "region — see docs/DECISIONS.md"
            )
        if not settings.vertex_zdr_enabled:
            raise ProviderNotConfigured(
                "VERTEX_ZDR_ENABLED is false; a patient's answers are not sent to a "
                "model that may retain them"
            )
        self._settings = settings
        self._model_id = settings.prefill_model_id
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:  # pragma: no cover
                raise ProviderNotConfigured(
                    "google-genai is not installed; install the 'gcp' extra"
                ) from exc
            self._client = genai.Client(
                vertexai=True,
                project=self._settings.vertex_project,
                location=self._settings.vertex_region,
            )
        return self._client

    async def suggest(
        self, *, free_text: str, questions: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        from google.genai import types

        client = self._get_client()
        prompt = (
            f"{PREFILL_INSTRUCTION}\n\n"
            f"Upcoming questions:\n{json.dumps(questions, ensure_ascii=False, indent=2)}\n\n"
            f"Patient's free text:\n{free_text}"
        )
        try:
            response = await client.aio.models.generate_content(
                model=self._model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PREFILL_RESPONSE_SCHEMA,
                    temperature=0.0,
                ),
            )
            parsed: dict[str, Any] = json.loads(response.text)
        except Exception:
            # A failed prefill call is not an error the caller has to handle
            # specially — the question is simply put to the patient, exactly as
            # it would be with no provider configured at all.
            logger.warning("prefill_call_failed", provider=self.name)
            return None
        return {
            item["field_id"]: item
            for item in parsed.get("suggestions", [])
            if isinstance(item, dict) and item.get("field_id")
        }
