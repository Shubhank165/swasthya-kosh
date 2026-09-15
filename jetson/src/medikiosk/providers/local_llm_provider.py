"""Open-vocabulary clinical fact extraction via a small local model on Ollama.

The heuristic extractor only recognizes a handful of hardcoded complaint phrases ("chest pain",
"abdominal pain", "headache") - anything else, "my ankle hurts", "kaan mein dard", "sugar badh gayi
hai", falls through as an unrecognized complaint. This is the same job OpenAIClinicalExtractor does
for the online profile, run locally: only explicitly stated facts, into the same strict schema, so
the red-flag rules and state machine downstream stay exactly as deterministic as before. Nothing
here decides urgency or picks the next question - it only decides which fields got mentioned.

It also reads through speech-recognition errors. Measured on this Jetson, gemma3:1b given
"दोदो दी से पेट में दर्द" (IndicConformer's rendering of "दो दिन से") still returned
duration "two days". Asked instead to *rewrite* the transcript it deleted the phrase, so the
patient's words are recorded as heard and only the extracted meaning is corrected.

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
    "You are the intake assistant of an Indian hospital kiosk. The user message is one patient "
    "utterance as heard by an offline speech recogniser, in Hindi, English or mixed Hinglish; "
    "it may contain recognition errors (for example 'दोदो दी से' means 'दो दिन से'). Read "
    "through such errors, but extract ONLY facts the patient explicitly stated. Return only the "
    "JSON schema supplied, and omit every field you have no value for - never write null, "
    "'unknown', '0' or 'not specified' as a placeholder. "
    "complaint: the body part or system in a few neutral English words ('ear pain', 'lower back "
    "pain', 'high blood sugar'), never a bare 'pain', and never a different body part than the "
    "one said. duration: the stated time period in English ('two days', 'since yesterday'). "
    "severity: a 0-10 number only if the patient gave one. A denial ('no vomiting', 'बुखार "
    "नहीं') is false. age_years only if stated. medications and allergies only if named. "
    "evidence: short exact fragments of the utterance that support each value. "
    'Example: "मुझे कान में दर्द है दोदो दी से और बुखार नहीं" -> {"complaint":"ear pain",'
    '"duration":"two days","fever":false,"evidence":["कान में दर्द","दोदो दी से","बुखार नहीं"]} '
    'Example: "my lower back has been hurting for a week, I take metformin" -> '
    '{"complaint":"lower back pain","duration":"one week","medications":["metformin"],'
    '"evidence":["lower back has been hurting","for a week","metformin"]} '
    'Example: "haan" -> {"evidence":["haan"]}'
)

EMPTY_UPDATE_KWARGS = {
    "complaint": None,
    "duration": None,
    "onset": None,
    "severity": None,
    "vomiting": None,
    "fever": None,
    "breathlessness": None,
    "chest_pain": None,
    "pain_radiation": None,
    "sweating": None,
    "active_bleeding": None,
    "altered_consciousness": None,
    "one_sided_weakness": None,
    "speech_difficulty": None,
    "pregnancy_possible": None,
    "age_years": None,
    "medications": [],
    "allergies": [],
    "evidence": [],
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
        # Nothing is required: the model emits only the fields it has a value for. Measured on
        # the Jetson, that alone took gemma3:1b from 5.3 s to 1.9 s a turn - the cost was
        # generating ~130 tokens of "null", not thinking. Missing keys become None on parse.
        schema = ClinicalUpdate.model_json_schema()
        schema.pop("required", None)
        self._schema = schema

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
            # keep_alive -1 pins the model: a reload between two patients costs seconds.
            "keep_alive": -1,
            "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 160},
        }
        try:
            request = urllib.request.Request(
                f"{self.base_url}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = json.loads(data.get("message", {}).get("content", "") or "{}")
            if not isinstance(content, dict):
                raise ValueError("model returned a non-object")
            # Only the keys the schema knows; omitted ones are the nulls we asked it not to write.
            known = {k: v for k, v in content.items() if k in EMPTY_UPDATE_KWARGS}
            update = ClinicalUpdate(**{**EMPTY_UPDATE_KWARGS, **known})
        except Exception:
            # A malformed response, a timeout, or Ollama being down must never surface as a
            # crashed turn or a fabricated fact - fall back to "nothing extracted" and let the
            # heuristic extractor (or the patient being asked again) carry the turn instead.
            return ClinicalUpdate(**{**EMPTY_UPDATE_KWARGS, "evidence": [transcript]})
        if transcript not in update.evidence:
            update.evidence.append(transcript)
        return update
