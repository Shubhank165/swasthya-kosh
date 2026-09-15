"""Maps a direct reply to the field the kiosk just asked about, in any supported language.

A patient answering "हाँ" or "ஆம்" says nothing an utterance-level extractor can attach to a field:
the meaning lives in the question that was asked. This module resolves that binding
deterministically, and only for the field the state machine actually asked for, so it can never
invent a fact the patient was not asked about.

English words are accepted alongside the session language, because patients mix "yes", "no" and
digits into every Indian language.
"""

from __future__ import annotations

import re

from medikiosk.models import QuestionSpec

AFFIRMATIVE: dict[str, frozenset[str]] = {
    "en": frozenset({"yes", "yeah", "yep", "yup", "correct", "right", "sure", "ok", "okay"}),
    "hi": frozenset({"हाँ", "हां", "हा", "जी", "हाजी", "हांजी", "जीहाँ", "बिलकुल", "बिल्कुल", "सही"}),
    "bn": frozenset({"হ্যাঁ", "হ্যা", "হা", "জি"}),
    "mr": frozenset({"हो", "होय", "हा"}),
    "te": frozenset({"అవును", "ఔను", "సరే"}),
    "ta": frozenset({"ஆம்", "ஆமாம்", "அம்", "சரி"}),
    "gu": frozenset({"હા", "હાજી"}),
    "kn": frozenset({"ಹೌದು", "ಹುಂ"}),
    "pa": frozenset({"ਹਾਂ", "ਹਾ", "ਜੀ"}),
}

# Copulas and existence verbs: "है", "आहे", "છે" all mean "is/exists".
#
# On their own they are a plain yes - a patient asked "क्या बुखार है?" who replies "है" means yes.
# Inside a longer sentence they are ordinary grammar, and matching them anywhere is how
# "मेरी उम्र चालीस साल है" ("my age is forty") set vomiting=true, and how "दर्द बहुत तेज़ है"
# ("the pain is severe") set active_bleeding=true and raised an emergency staff alert for a
# patient who never mentioned bleeding. A red flag invented from grammar is worse than no red
# flag: it teaches staff to distrust the alerts that are real.
#
# So these count as agreement only when they are the whole reply. A longer sentence returns no
# polarity, which leaves the field unset and lets the kiosk ask again.
COPULA_AFFIRMATIVE: dict[str, frozenset[str]] = {
    "en": frozenset(),
    "hi": frozenset({"है", "हैं"}),
    "bn": frozenset({"আছে", "হয়েছে"}),
    "mr": frozenset({"आहे"}),
    "te": frozenset({"ఉంది", "అయ్యాయి"}),
    "ta": frozenset({"இருக்கு", "உள்ளது", "வந்தது"}),
    "gu": frozenset({"છે", "થઈ"}),
    "kn": frozenset({"ಇದೆ", "ಆಗಿದೆ"}),
    "pa": frozenset({"ਹੈ", "ਆਈ"}),
}

# "है" as the entire answer, or with one filler word ("जी है", "हाँ है").
MAX_COPULA_ANSWER_TOKENS = 2

NEGATIVE: dict[str, frozenset[str]] = {
    "en": frozenset({"no", "nope", "nah", "never", "negative"}),
    "hi": frozenset({"नहीं", "नही", "ना"}),
    "bn": frozenset({"না", "নেই", "নয়", "নাই"}),
    "mr": frozenset({"नाही", "नको", "नाहीये"}),
    "te": frozenset({"లేదు", "కాదు"}),
    "ta": frozenset({"இல்லை", "இல்ல", "இல்லெ", "இலை"}),
    "gu": frozenset({"ના", "નથી", "નહીં"}),
    "kn": frozenset({"ಇಲ್ಲ", "ಅಲ್ಲ"}),
    "pa": frozenset({"ਨਹੀਂ", "ਨਹੀ", "ਨਾ"}),
}

# Checked as substrings: "I do not know" is a phrase, not a token, in every language.
UNKNOWN: dict[str, frozenset[str]] = {
    "en": frozenset({"i don't know", "dont know", "do not know", "not sure", "no idea"}),
    "hi": frozenset({"पता नहीं", "मालूम नहीं", "याद नहीं"}),
    "bn": frozenset({"জানি না", "মনে নেই"}),
    "mr": frozenset({"माहीत नाही", "आठवत नाही"}),
    "te": frozenset({"తెలియదు", "గుర్తు లేదు"}),
    "ta": frozenset({"தெரியாது", "நினைவில் இல்லை"}),
    "gu": frozenset({"ખબર નથી", "યાદ નથી"}),
    "kn": frozenset({"ಗೊತ್ತಿಲ್ಲ", "ನೆನಪಿಲ್ಲ"}),
    "pa": frozenset({"ਪਤਾ ਨਹੀਂ", "ਯਾਦ ਨਹੀਂ"}),
}

NUMBER_WORDS: dict[str, dict[str, int]] = {
    "en": {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twenty": 20, "thirty": 30,
        "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    },
    "hi": {
        "शून्य": 0, "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6,
        "छे": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10, "बीस": 20, "तीस": 30,
        "चालीस": 40, "पचास": 50, "साठ": 60, "सत्तर": 70, "अस्सी": 80, "नब्बे": 90,
        # Frequent ASR confusions, safe because a value is only read for the field just asked.
        "साथ": 7, "दश": 10,
    },
    "bn": {
        "শূন্য": 0, "এক": 1, "দুই": 2, "তিন": 3, "চার": 4, "পাঁচ": 5, "ছয়": 6, "সাত": 7,
        "আট": 8, "নয়": 9, "দশ": 10, "বিশ": 20, "ত্রিশ": 30, "চল্লিশ": 40, "পঞ্চাশ": 50,
        "ষাট": 60, "সত্তর": 70, "আশি": 80, "নব্বই": 90,
    },
    "mr": {
        "शून्य": 0, "एक": 1, "दोन": 2, "तीन": 3, "चार": 4, "पाच": 5, "सहा": 6, "सात": 7,
        "आठ": 8, "नऊ": 9, "दहा": 10, "वीस": 20, "तीस": 30, "चाळीस": 40, "पन्नास": 50,
        "साठ": 60, "सत्तर": 70, "ऐंशी": 80, "नव्वद": 90,
    },
    "te": {
        "సున్నా": 0, "ఒకటి": 1, "రెండు": 2, "మూడు": 3, "నాలుగు": 4, "ఐదు": 5, "ఆరు": 6,
        "ఏడు": 7, "ఎనిమిది": 8, "తొమ్మిది": 9, "పది": 10, "ఇరవై": 20, "ముప్పై": 30,
        "నలభై": 40, "యాభై": 50, "అరవై": 60, "డెబ్బై": 70, "ఎనభై": 80, "తొంభై": 90,
    },
    "ta": {
        "பூஜ்யம்": 0, "ஒன்று": 1, "இரண்டு": 2, "மூன்று": 3, "நான்கு": 4, "ஐந்து": 5,
        "ஆறு": 6, "ஏழு": 7, "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10, "இருபது": 20,
        "முப்பது": 30, "நாற்பது": 40, "ஐம்பது": 50, "அறுபது": 60, "எழுபது": 70,
        "எண்பது": 80, "தொண்ணூறு": 90,
    },
    "gu": {
        "શૂન્ય": 0, "એક": 1, "બે": 2, "ત્રણ": 3, "ચાર": 4, "પાંચ": 5, "છ": 6, "સાત": 7,
        "આઠ": 8, "નવ": 9, "દસ": 10, "વીસ": 20, "ત્રીસ": 30, "ચાલીસ": 40, "પચાસ": 50,
        "સાઠ": 60, "સિત્તેર": 70, "એંસી": 80, "નેવું": 90,
    },
    "kn": {
        "ಸೊನ್ನೆ": 0, "ಒಂದು": 1, "ಎರಡು": 2, "ಮೂರು": 3, "ನಾಲ್ಕು": 4, "ಐದು": 5, "ಆರು": 6,
        "ಏಳು": 7, "ಎಂಟು": 8, "ಒಂಬತ್ತು": 9, "ಹತ್ತು": 10, "ಇಪ್ಪತ್ತು": 20, "ಮೂವತ್ತು": 30,
        "ನಲವತ್ತು": 40, "ಐವತ್ತು": 50, "ಅರವತ್ತು": 60, "ಎಪ್ಪತ್ತು": 70, "ಎಂಬತ್ತು": 80,
        "ತೊಂಬತ್ತು": 90,
    },
    "pa": {
        "ਸਿਫ਼ਰ": 0, "ਇੱਕ": 1, "ਦੋ": 2, "ਤਿੰਨ": 3, "ਚਾਰ": 4, "ਪੰਜ": 5, "ਛੇ": 6, "ਸੱਤ": 7,
        "ਅੱਠ": 8, "ਨੌਂ": 9, "ਦਸ": 10, "ਵੀਹ": 20, "ਤੀਹ": 30, "ਚਾਲੀ": 40, "ਪੰਜਾਹ": 50,
        "ਸੱਠ": 60, "ਸੱਤਰ": 70, "ਅੱਸੀ": 80, "ਨੱਬੇ": 90,
    },
}

BOOLEAN_FIELDS = frozenset(
    {
        "vomiting", "fever", "breathlessness", "chest_pain", "pain_radiation", "sweating",
        "active_bleeding", "altered_consciousness", "one_sided_weakness", "speech_difficulty",
        "pregnancy_possible",
    }
)


def _base(language: str | None) -> str:
    code = (language or "en").lower()
    if code in {"hinglish", "hi-latn"}:
        return "hi"
    return code[:2] if code[:2] in NUMBER_WORDS else "en"


def _tokens(transcript: str) -> list[str]:
    return [t for t in re.split(r"[\s,।॥.!?|]+", transcript.strip().lower()) if t]


def _number(transcript: str, language: str) -> int | None:
    digits = re.search(r"\b(\d{1,3})\b", transcript)
    if digits:
        return int(digits.group(1))
    words = {**NUMBER_WORDS["en"], **NUMBER_WORDS[language]}
    total = None
    for token in _tokens(transcript):
        if token in words:
            total = (total or 0) + words[token]
    return total


def _polarity(transcript: str, language: str) -> bool | None:
    tokens = _tokens(transcript)
    text = " ".join(tokens)
    if any(phrase in text for phrase in UNKNOWN["en"] | UNKNOWN[language]):
        return None
    if any(token in NEGATIVE["en"] | NEGATIVE[language] for token in tokens):
        return False
    if any(token in AFFIRMATIVE["en"] | AFFIRMATIVE[language] for token in tokens):
        return True
    if len(tokens) <= MAX_COPULA_ANSWER_TOKENS and any(
        token in COPULA_AFFIRMATIVE[language] for token in tokens
    ):
        return True
    return None


def direct_answer(
    question: QuestionSpec,
    transcript: str,
    language: str | None = "en",
) -> dict[str, object]:
    """Value the reply carries for the asked field, or {} when it carries none.

    Free-text fields keep the patient's own words: normalizing them here would raise certainty
    the patient never expressed.
    """

    text = transcript.strip()
    if not text:
        return {}

    code = _base(language)
    field = question.target_field

    if field in BOOLEAN_FIELDS:
        polarity = _polarity(text, code)
        return {} if polarity is None else {field: polarity}

    if field == "severity":
        value = _number(text, code)
        return {field: value} if value is not None and 0 <= value <= 10 else {}

    if field == "age_years":
        value = _number(text, code)
        return {field: value} if value is not None and 0 <= value <= 125 else {}

    if field in {"complaint", "duration", "onset"}:
        return {field: text}

    return {}
