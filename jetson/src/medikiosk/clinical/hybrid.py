"""Combines the deterministic keyword extractor with the open-vocabulary local LLM.

The heuristic extractor is fast (regex, no network) and exact wherever it fires - "no chest pain"
is an unambiguous denial, "पेट में दर्द तीन दिन से" is an unambiguous duration match. Its weakness
is recall: it only recognizes complaints and phrases someone hardcoded in advance. The LLM's
weakness is precision on a 1B model - it can drop a duration the heuristic would have caught
outright, or occasionally misread a language it knows less well.

The merge rule follows from that: for every field, the heuristic's answer wins whenever it has
one; the LLM only fills in fields the heuristic left null. That makes the LLM strictly additive -
it can only make the record more complete, never override a fact the deterministic matcher already
established. A patient describing "my ankle hurts" or "sugar badh gayi hai" - nothing in the
heuristic's fixed phrase list - is exactly the case this exists for.

Before the LLM's values are used at all they pass through clinical/grounding.py: a value the
transcript does not support (a body part never mentioned, a number never said) is dropped. On
this Jetson gemma3:1b copies its prompt examples when it does not understand an utterance, and a
schema cannot tell a copied "ear pain" from a real one. The transcript can.

`severity` is excluded even so: on-device testing had gemma3:1b invent a 0-10 score from
adjectives alone ("a bad headache" -> 10; unspecified Hindi ear pain -> 6) despite the prompt
saying not to. red_flags.py compares severity against numeric thresholds to decide an EMERGENCY
alert - a fabricated number there is not a missed detail, it is a false or suppressed alert. The
dedicated ask_severity question and its direct_answer() binding already capture severity whenever
a patient actually states one; nothing is lost by leaving this one field to the deterministic path.
"""

from __future__ import annotations

from typing import Protocol

from medikiosk.clinical.grounding import ground
from medikiosk.models import ClinicalUpdate

# severity is deliberately absent - see the module docstring. It stays heuristic/direct-answer only.
SCALAR_FIELDS = (
    "complaint",
    "duration",
    "onset",
    "vomiting",
    "fever",
    "breathlessness",
    "chest_pain",
    "pain_radiation",
    "sweating",
    "active_bleeding",
    "altered_consciousness",
    "one_sided_weakness",
    "speech_difficulty",
    "pregnancy_possible",
    "age_years",
)


class Extractor(Protocol):
    async def extract(self, transcript: str) -> ClinicalUpdate: ...


class HybridClinicalExtractor:
    def __init__(self, heuristic: Extractor, llm: Extractor | None) -> None:
        self.heuristic = heuristic
        self.llm = llm

    async def extract(self, transcript: str) -> ClinicalUpdate:
        primary = await self.heuristic.extract(transcript)
        if self.llm is None:
            return primary

        fallback = ground(await self.llm.extract(transcript), transcript)
        merged = primary.model_copy(deep=True)
        for field in SCALAR_FIELDS:
            if getattr(merged, field) is None:
                setattr(merged, field, getattr(fallback, field))
        for field in ("medications", "allergies"):
            existing = getattr(merged, field)
            for value in getattr(fallback, field):
                if value and value not in existing:
                    existing.append(value)
        for value in fallback.evidence:
            if value not in merged.evidence:
                merged.evidence.append(value)
        return merged
