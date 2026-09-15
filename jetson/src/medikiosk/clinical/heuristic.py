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
    "slurred speech",
    "speech is slurred",
    "speech slurred",
    "slurring",
    "difficulty speaking",
    "difficulty in speaking",
    "trouble speaking",
    "hard to speak",
    "unable to speak",
    "can't speak",
    "cannot speak",
    "words are not coming",
    "words don't come",
    "speech has gone",
    "बोलने में दिक्कत",
    "बोलने में परेशानी",
    "बोल नहीं पा",
    "जुबान लड़खड़ा",
    "आवाज़ लड़खड़ा",
)


# Complaint phrases in English, Devanagari and romanised Hindi as the recogniser writes it
# ("pet me dard", "sir dard"), each mapped to the canonical English the routing table and the
# hospital's section map expect. Order matters only where one phrase contains another.
COMPLAINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "chest pain",
            "सीने में दर्द",
            "छाती में दर्द",
            "seene me dard",
            "seene mein dard",
            "seena dard",
            "chhati me dard",
            "chati me dard",
            "chest me dard",
        ),
        "chest pain",
    ),
    (
        (
            "stomach pain",
            "lower abdomen",
            "pain in abdomen",
            "abdomen pain",
            "pain in stomach",
            "stomach ache",
            "abdominal pain",
            "stomach ache",
            "belly pain",
            "पेट में दर्द",
            "पेट दर्द",
            "पेट में मरोड़",
            "pet me dard",
            "pet mein dard",
            "pet dard",
            "pet me marod",
            "pet me jalan",
            "पेट में जलन",
        ),
        "abdominal pain",
    ),
    (
        (
            "headache",
            "head pain",
            "head ache",
            "सिर दर्द",
            "सिरदर्द",
            "सिर में दर्द",
            "सर दर्द",
            "sir dard",
            "sar dard",
            "sir me dard",
            "sar me dard",
            "sir mein dard",
        ),
        "headache",
    ),
    (
        (
            "ear pain",
            "earache",
            "ear ache",
            "कान में दर्द",
            "कान दर्द",
            "kaan me dard",
            "kaan mein dard",
            "kan me dard",
            "kaan dard",
        ),
        "ear pain",
    ),
    (
        (
            "back pain",
            "backache",
            "lower back",
            "पीठ में दर्द",
            "कमर में दर्द",
            "कमर दर्द",
            "peeth me dard",
            "kamar me dard",
            "kamar mein dard",
            "kamar dard",
        ),
        "back pain",
    ),
    (
        (
            "throat pain",
            "sore throat",
            "गले में दर्द",
            "गला खराब",
            "gale me dard",
            "gala kharab",
            "gale me kharash",
            "गले में खराश",
        ),
        "throat pain",
    ),
    (
        (
            "knee pain",
            "घुटने में दर्द",
            "घुटनों में दर्द",
            "ghutne me dard",
            "ghutno me dard",
            "ghutne mein dard",
        ),
        "knee pain",
    ),
    (
        ("toothache", "tooth pain", "दांत में दर्द", "दाँत में दर्द", "daant me dard", "dant me dard"),
        "tooth pain",
    ),
    (
        ("eye pain", "आँख में दर्द", "आंख में दर्द", "aankh me dard", "ankh me dard"),
        "eye pain",
    ),
    (
        (
            "joint pain",
            "जोड़ों में दर्द",
            "jodo me dard",
            "jodon me dard",
            "body pain",
            "बदन दर्द",
            "badan dard",
        ),
        "joint pain",
    ),
    (("sugar badh", "sugar high", "high sugar", "शुगर बढ़", "diabetes", "मधुमेह"), "high blood sugar"),
    (("cough", "खांसी", "खाँसी", "khansi", "khaansi"), "cough"),
    (("loose motion", "diarrhoea", "diarrhea", "दस्त", "dast"), "loose motions"),
    (("fever", "बुखार", "bukhar", "bukhaar"), "fever"),
)

# Numbers and units as spoken and as romanised, for durations like "paanch din se".
_NUMBER_WORDS = (
    r"\d+|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty"
    r"|एक|दो|तीन|चार|पाँच|पांच|छह|सात|आठ|नौ|दस|पंद्रह|बीस"
    r"|ek|do|teen|tin|char|chaar|paanch|panch|chhe|che|saat|sat|aath|ath|nau|das|dus|pandrah|bees"
)
_UNIT_WORDS = (
    r"days?|weeks?|months?|years?|hours?"
    r"|दिन[ों]?|हफ्त[ेों]*|सप्ताह[ों]*|महीन[ेों]*|साल[ों]?|घंट[ेों]*"
    r"|din[o]?|dino|hafte|hafta|hafton|saptah|mahine|mahina|mahino|saal|ghante|ghanta"
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
            rf"\b((?:{_NUMBER_WORDS})\s*(?:{_UNIT_WORDS}))"
            # Not \b: Devanagari vowel signs are combining marks (category Mn), which Python does
            # not count as word characters, so a trailing \b matched *before* the matra and clipped
            # "दो हफ्ते" to "दो हफ्त" on the doctor's sheet. Reject a following letter or any
            # Devanagari codepoint instead.
            r"(?![\wऀ-ॿ])",
            text,
        )
        duration = duration_match.group(1).strip() if duration_match else None
        if duration is None and re.search(
            r"\b(?:kal se|since yesterday|from yesterday)\b|कल से", text
        ):
            duration = "since yesterday"
        return ClinicalUpdate(
            complaint=complaint,
            duration=duration,
            onset=None,
            severity=int(severity_match.group(1)) if severity_match else None,
            vomiting=self._boolean(
                text,
                ("vomit", "उल्टी", "ulti", "ultiyan", "ubkai"),
                ("no vomit", "उल्टी नहीं", "ulti nahi", "ulti nahin"),
            ),
            fever=self._boolean(
                text,
                ("fever", "बुखार", "bukhar", "bukhaar"),
                ("no fever", "बुखार नहीं", "bukhar nahi", "bukhar nahin"),
            ),
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
                    "saans lene me",
                    "saans lene mein",
                    "saans phool",
                    "sans lene me",
                    "dam phool",
                ),
                (
                    "no breathlessness",
                    "not short of breath",
                    "breathing is fine",
                    "साँस ठीक",
                    "सांस ठीक",
                    "saans theek",
                ),
            ),
            chest_pain=self._boolean(
                text,
                (
                    "chest pain",
                    "सीने में दर्द",
                    "छाती में दर्द",
                    "seene me dard",
                    "seene mein dard",
                    "chhati me dard",
                    "chati me dard",
                    "chest me dard",
                ),
                ("no chest pain", "seene me dard nahi"),
            ),
            pain_radiation=self._boolean(
                text,
                ("moves to my arm", "radiates", "बाँह", "जबड़े"),
                ("does not move", "no radiation"),
            ),
            sweating=self._boolean(
                text, ("sweating", "पसीना", "paseena", "pasina"), ("no sweating", "paseena nahi")
            ),
            active_bleeding=self._boolean(
                text,
                ("bleeding", "खून बह", "khoon beh", "khoon aa", "khun beh", "khoon nikal"),
                ("no bleeding", "खून नहीं", "khoon nahi"),
            ),
            altered_consciousness=self._boolean(
                text,
                ("unconscious", "fainted", "बेहोश", "behosh", "chakkar aa"),
                ("not unconscious", "behosh nahi"),
            ),
            one_sided_weakness=(
                None if "no weakness" in text else (True if _side_weakness(text) else None)
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
        for terms, canonical in COMPLAINTS:
            if any(term in text for term in terms):
                return canonical
        return None
