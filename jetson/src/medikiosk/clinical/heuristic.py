import re

from medikiosk.models import ClinicalUpdate

# Stroke wording, matched by proximity rather than by exact phrase.
#
# These two fields each raise an EMERGENCY on their own, and they are reachable only from what a
# patient says in their own words - no questionnaire asks them. The original lists were exact
# substrings ("one side weak", "slurred speech"), so the ordinary way of saying it - "my right
# side has gone weak", "my speech is slurred" - matched nothing and the alert never fired. With
# Ollama down the extractor is heuristic-only, and that was the whole of the kiosk's stroke
# detection.
#
# A side word near a weakness word, in either order, is the pattern. Bare "weak" is deliberately
# not enough: "I feel weak" is fatigue, and a false EMERGENCY is its own harm.
_SIDE = (
    r"(?:one|right|left|either|1)[\s-]*(?:side|sided|arm|leg|hand|foot|face)"
    r"|एक\s*(?:तरफ|ओर)|दाहिन\w*|दायां|बाय\w*|बाई"
)
_WEAKNESS = (
    r"weak\w*|numb\w*|paralys\w*|paraly[sz]\w*|no strength"
    r"|can'?t move|cannot move|not moving|won'?t move"
    r"|कमज़?ोर\w*|लकवा|सुन्न|हिल नहीं"
)
_NEAR = 40


def _side_weakness(text: str) -> bool:
    """True when a side word and a weakness word appear close together, in either order."""

    for side in re.finditer(_SIDE, text):
        window = text[max(0, side.start() - _NEAR) : side.end() + _NEAR]
        if re.search(_WEAKNESS, window):
            return True
    return False


_SPEECH_POSITIVE = (
    "slurred speech", "speech is slurred", "speech slurred", "slurring",
    "difficulty speaking", "difficulty in speaking", "trouble speaking",
    "hard to speak", "unable to speak", "can't speak", "cannot speak",
    "words are not coming", "words don't come", "speech has gone",
    "बोलने में दिक्कत", "बोलने में परेशानी", "बोल नहीं पा", "जुबान लड़खड़ा", "आवाज़ लड़खड़ा",
)


class HeuristicClinicalExtractor:
    """Small deterministic fallback for demos and offline integration tests."""

    async def extract(self, transcript: str) -> ClinicalUpdate:
        text = transcript.lower()
        complaint = self._complaint(text)
        severity_match = re.search(r"(?:severity|pain|दर्द).*?\b(10|[0-9])\b", text)
        age_match = re.search(r"\b(?:i am|age is|उम्र)\s*(\d{1,3})\b", text)
        duration_match = re.search(
            # English only. "से" was here too, but it is a Hindi *post*position - it follows the
            # phrase ("दो हफ्ते से"), where for/since precede it. Anchoring on it the same way made
            # "मुझे दो हफ्ते से पेट में दर्द है" capture everything to its right, putting the
            # complaint "पेट में दर्द है" into the duration field on the doctor's sheet. Hindi
            # durations are matched by the quantity + unit pattern below instead, which needs no
            # postposition at all.
            r"\b(?:for|since)\s+(.{1,40}?)(?:\s+and\s+|[,\.!?]|$)",
            text,
        ) or re.search(
            # A patient answering the duration question directly says "three days", not "for
            # three days" - no preposition to anchor on. Match a bare quantity + unit instead, one
            # group covering the whole phrase so it works the same way as the pattern above.
            r"\b((?:\d+|one|two|three|four|five|six|seven|eight|nine|ten"
            r"|एक|दो|तीन|चार|पाँच|पांच|छह|सात|आठ|नौ|दस)"
            r"\s*"
            r"(?:days?|weeks?|months?|hours?|दिन[ों]?|हफ्त[ेों]*|सप्ताह[ों]*|महीन[ेों]*|घंट[ेों]*))"
            # Not \b: Devanagari vowel signs are combining marks (category Mn), which Python does
            # not count as word characters, so a trailing \b matched *before* the matra and clipped
            # "दो हफ्ते" to "दो हफ्त" on the doctor's sheet. Reject a following letter or any
            # Devanagari codepoint instead.
            r"(?![\wऀ-ॿ])",
            text,
        )
        return ClinicalUpdate(
            complaint=complaint,
            duration=duration_match.group(1).strip() if duration_match else None,
            onset=None,
            severity=int(severity_match.group(1)) if severity_match else None,
            vomiting=self._boolean(text, ("vomit", "उल्टी"), ("no vomit", "उल्टी नहीं")),
            fever=self._boolean(text, ("fever", "बुखार"), ("no fever", "बुखार नहीं")),
            breathlessness=self._boolean(
                text,
                (
                    "breathless",
                    "short of breath",
                    "difficulty breathing",
                    "can't breathe",
                    "cannot breathe",
                    "साँस लेने में",
                    "सांस लेने में",
                ),
                (
                    "no breathlessness",
                    "not short of breath",
                    "breathing is fine",
                    "साँस ठीक",
                    "सांस ठीक",
                ),
            ),
            chest_pain=self._boolean(
                text, ("chest pain", "सीने में दर्द", "छाती में दर्द"), ("no chest pain",)
            ),
            pain_radiation=self._boolean(
                text,
                ("moves to my arm", "radiates", "बाँह", "जबड़े"),
                ("does not move", "no radiation"),
            ),
            sweating=self._boolean(text, ("sweating", "पसीना"), ("no sweating",)),
            active_bleeding=self._boolean(text, ("bleeding", "खून बह"), ("no bleeding", "खून नहीं")),
            altered_consciousness=self._boolean(
                text, ("unconscious", "fainted", "बेहोश"), ("not unconscious",)
            ),
            one_sided_weakness=(
                None
                if "no weakness" in text
                else (True if _side_weakness(text) else None)
            ),
            speech_difficulty=self._boolean(text, _SPEECH_POSITIVE, ("no difficulty speaking",)),
            pregnancy_possible=None,
            age_years=int(age_match.group(1)) if age_match else None,
            medications=[],
            allergies=[],
            evidence=[transcript],
        )

    @staticmethod
    def _boolean(text: str, positive: tuple[str, ...], negative: tuple[str, ...]) -> bool | None:
        if any(term in text for term in negative):
            return False
        if any(term in text for term in positive):
            return True
        return None

    @staticmethod
    def _complaint(text: str) -> str | None:
        if any(term in text for term in ("chest pain", "सीने में दर्द", "छाती में दर्द")):
            return "chest pain"
        if any(term in text for term in ("stomach pain", "abdominal pain", "पेट में दर्द")):
            return "abdominal pain"
        if "headache" in text or "सिर दर्द" in text:
            return "headache"
        return None
