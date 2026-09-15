"""Open-vocabulary clinical fact extraction via a small local model on Ollama.

The heuristic extractor only recognizes a handful of hardcoded complaint phrases ("chest pain",
"abdominal pain", "headache") - anything else, "my ankle hurts", "kaan mein dard", "sugar badh gayi
hai", falls through as an unrecognized complaint. This is the same job OpenAIClinicalExtractor does
for the online profile, run locally: only explicitly stated facts, into the same strict schema, so
the red-flag rules and state machine downstream stay exactly as deterministic as before. Nothing
here decides urgency or picks the next question - it only decides which fields got mentioned.

Ollama's structured-output mode (`format: <json schema>`) is what makes this safe to trust
structurally: the model cannot return a field the schema does not define, because ClinicalUpdate
already sets `extra="forbid"`. It can still misread a language it does not know well, invent a
placeholder instead of leaving a field null, or - once, in testing - swap a described body part
for a different one entirely (Qwen2.5 1.5B turned "पीठ में दर्द, कमर के नीचे" (lower back pain)
into "pain in the chest" on this Jetson). Neither failure is something a JSON schema can catch, so
this class's output is never trusted alone - see HybridClinicalExtractor.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

from medikiosk.models import ClinicalUpdate

INSTRUCTIONS = (
    "You extract explicitly stated clinical intake facts from one patient utterance. "
    "Return only the supplied JSON schema. Do not diagnose, infer unstated facts, or convert "
    "uncertainty into certainty. A denial such as 'no vomiting' is false; absence of a mention "
    "is null - never invent a placeholder like '0', 'unknown', or 'not specified'; use JSON "
    "null for any field the patient did not mention. The complaint must name the body part or "
    "system the patient mentioned, not a bare word like 'pain' - 'कान में दर्द' is 'ear pain', "
    "not 'pain'. Keep it to a few neutral words and never substitute a different body part or a "
    "different symptom than the one actually said. Severity is only a 0-10 number if the "
    "speaker explicitly provides it. Duration is only set if the patient stated a time period; "
    "otherwise it is null, never a word describing severity or certainty. Evidence must contain "
    "short exact fragments from the utterance supporting the extracted values.\n\n"
    'Example. Utterance: "I have a headache and I feel dizzy"\n'
    '{"complaint":"headache","duration":null,"onset":null,"severity":null,'
    '"vomiting":null,"fever":null,"breathlessness":null,"chest_pain":null,'
    '"pain_radiation":null,"sweating":null,"active_bleeding":null,'
    '"altered_consciousness":null,"one_sided_weakness":null,"speech_difficulty":null,'
    '"pregnancy_possible":null,"age_years":null,"medications":[],"allergies":[],'
    '"evidence":["headache","feel dizzy"]}\n\n'
    'Example. Utterance: "मुझे कान में दर्द है"\n'
    '{"complaint":"ear pain","duration":null,"onset":null,"severity":null,'
    '"vomiting":null,"fever":null,"breathlessness":null,"chest_pain":null,'
    '"pain_radiation":null,"sweating":null,"active_bleeding":null,'
    '"altered_consciousness":null,"one_sided_weakness":null,"speech_difficulty":null,'
    '"pregnancy_possible":null,"age_years":null,"medications":[],"allergies":[],'
    '"evidence":["कान में दर्द"]}'
)

EMPTY_UPDATE_KWARGS = {
    "complaint": None, "duration": None, "onset": None, "severity": None,
    "vomiting": None, "fever": None, "breathlessness": None, "chest_pain": None,
    "pain_radiation": None, "sweating": None, "active_bleeding": None,
    "altered_consciousness": None, "one_sided_weakness": None, "speech_difficulty": None,
    "pregnancy_possible": None, "age_years": None,
    "medications": [], "allergies": [], "evidence": [],
}


class LocalLLMClinicalExtractor:
    """Talks to a resident Ollama model. Never raises: a bad or slow response degrades to an
    all-null update rather than blocking a turn or guessing at a clinical fact."""

    def __init__(
        self,
        model: str = "gemma3:1b",
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 20.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._schema = ClinicalUpdate.model_json_schema()

    def health(self) -> bool:
        try:
            request = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(request, timeout=5) as response:
                tags = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
            return False
        return any(m.get("name", "").startswith(self.model) for m in tags.get("models", []))

    async def extract(self, transcript: str) -> ClinicalUpdate:
        return await asyncio.to_thread(self._extract_sync, transcript)

    def _extract_sync(self, transcript: str) -> ClinicalUpdate:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": INSTRUCTIONS},
                {"role": "user", "content": transcript},
            ],
            "format": self._schema,
            "stream": False,
            "options": {"temperature": 0},
        }
        try:
            request = urllib.request.Request(
                f"{self.base_url}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data.get("message", {}).get("content", "")
            update = ClinicalUpdate.model_validate_json(content)
        except Exception:
            # A malformed response, a timeout, or Ollama being down must never surface as a
            # crashed turn or a fabricated fact - fall back to "nothing extracted" and let the
            # heuristic extractor (or the patient being asked again) carry the turn instead.
            return ClinicalUpdate(**{**EMPTY_UPDATE_KWARGS, "evidence": [transcript]})
        if transcript not in update.evidence:
            update.evidence.append(transcript)
        return update
