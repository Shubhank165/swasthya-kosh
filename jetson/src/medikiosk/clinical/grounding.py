"""Keep only what the patient actually said: a check on the local LLM's extraction.

Why this exists
---------------
gemma3:1b on the Jetson copies its own prompt examples when it does not understand an utterance.
Given "pet me dard hai paanch din se" it returned complaint "ear pain", duration "two days" -
both lifted verbatim from the few-shot example - and once wrote duration "two days" for an
English sentence that said "five days". A JSON schema cannot catch that: the values are
well-formed, they are just about a different patient.

So the model proposes and this module disposes. A duration or age is kept only if its number
appears in the transcript; a complaint only if the body part or system it names was mentioned,
in English, Hinglish or Devanagari; a symptom flag only if that symptom was mentioned at all
(a denial mentions it too); a medication only if its name is literally there. Anything that
fails is dropped to None, which means the kiosk asks - the failure mode we can live with.

The lexicon is small and Hindi-belt-centred on purpose. A term missing from it costs one extra
question; a term wrongly present costs a wrong line on a physician's sheet.
"""

from __future__ import annotations

import re

from medikiosk.clinical.answers import NUMBER_WORDS
from medikiosk.models import ClinicalUpdate

# Spoken-Hindi numbers as the ASR tends to romanise them, on top of the en/hi tables.
HINGLISH_NUMBERS: dict[str, int] = {
    "ek": 1,
    "do": 2,
    "teen": 3,
    "tin": 3,
    "char": 4,
    "chaar": 4,
    "paanch": 5,
    "panch": 5,
    "pach": 5,
    "chhe": 6,
    "che": 6,
    "chah": 6,
    "saat": 7,
    "sat": 7,
    "aath": 8,
    "ath": 8,
    "nau": 9,
    "das": 10,
    "dus": 10,
    "gyarah": 11,
    "barah": 12,
    "pandrah": 15,
    "bees": 20,
    "tees": 30,
    "chalis": 40,
    "pachas": 50,
    "pachpan": 55,
    "saath": 60,
    "sattar": 70,
    "assi": 80,
    "nabbe": 90,
}
NUMBERS: dict[str, int] = {**NUMBER_WORDS["en"], **NUMBER_WORDS["hi"], **HINGLISH_NUMBERS}
NUMBERS.update({"eleven": 11, "twelve": 12, "fifteen": 15, "half": 0})
YESTERDAY = ("yesterday", "kal", "कल", "last night", "raat", "रात")

# English body part / system -> how a patient from the Hindi belt says it, in any script.
BODY: dict[str, tuple[str, ...]] = {
    "abdomen": ("abdom", "stomach", "belly", "tummy", "pet", "पेट", "gastric"),
    "head": ("head", "migraine", "sir", "sar", "सिर", "सर"),
    "ear": ("ear", "kaan", "kan", "कान"),
    "chest": ("chest", "seene", "seena", "chhati", "chati", "सीने", "छाती", "सीना"),
    "back": ("back", "spine", "peeth", "pith", "kamar", "पीठ", "कमर"),
    "throat": ("throat", "gala", "gale", "गला", "गले"),
    "knee": ("knee", "ghutn", "घुटन"),
    "tooth": ("tooth", "teeth", "dental", "daant", "dant", "दांत", "दाँत"),
    "eye": ("eye", "vision", "aankh", "ankh", "आँख", "आंख"),
    "ankle": ("ankle", "takhna", "टखन"),
    "leg": ("leg", "foot", "feet", "pair", "पैर", "टांग", "tang"),
    "hand": ("hand", "arm", "wrist", "haath", "hath", "हाथ", "बाँह", "bazu"),
    "shoulder": ("shoulder", "kandha", "kandhe", "कंधे", "कंधा"),
    "neck": ("neck", "gardan", "गर्दन"),
    "joint": ("joint", "jod", "जोड़"),
    "skin": ("skin", "rash", "itch", "khujli", "खुजली", "त्वचा", "dane", "दाने"),
    "urine": ("urin", "peshab", "पेशाब", "bladder"),
    "sugar": ("sugar", "diabet", "शुगर", "मधुमेह"),
    "blood pressure": ("pressure", "bp", "ब्लड प्रेशर"),
    "fever": ("fever", "bukhar", "bukhaar", "बुखार", "temperature"),
    "cough": ("cough", "khansi", "khaansi", "खांसी", "खाँसी"),
    "cold": ("cold", "sardi", "jukam", "zukam", "सर्दी", "जुकाम"),
    "breath": ("breath", "saans", "sans", "सांस", "साँस", "asthma", "dama", "दमा"),
    "heart": ("heart", "dil", "दिल", "palpitat", "dhadkan", "धड़कन"),
    "weakness": ("weak", "kamzor", "kamjor", "कमज़ोर", "कमजोर", "thakan", "थकान", "fatigue"),
    "dizziness": ("dizz", "chakkar", "चक्कर", "giddy"),
    "vomiting": ("vomit", "ulti", "उल्टी", "nausea", "ubkai", "उबकाई"),
    "loose motion": ("diarr", "loose", "dast", "दस्त", "motion"),
    "constipation": ("constipat", "kabz", "कब्ज"),
    "period": ("period", "menstru", "mahwari", "माहवारी", "mc"),
    "pregnan": ("pregnan", "garbh", "गर्भ"),
    "injury": ("injur", "fell", "fall", "chot", "चोट", "accident", "gir", "गिर"),
    "swelling": ("swell", "sujan", "सूजन"),
    "burn": ("burn", "jal", "जल"),
}

# Which words in the transcript license each symptom flag, true or false.
SYMPTOMS: dict[str, tuple[str, ...]] = {
    "fever": BODY["fever"],
    "vomiting": BODY["vomiting"],
    "breathlessness": BODY["breath"],
    "chest_pain": BODY["chest"],
    "pain_radiation": ("radiat", "spread", "arm", "jaw", "बाँह", "जबड़", "haath", "हाथ", "फैल"),
    "sweating": ("sweat", "paseena", "pasina", "पसीना"),
    "active_bleeding": ("bleed", "blood", "khoon", "khun", "खून", "रक्त"),
    "altered_consciousness": (
        "unconscious",
        "faint",
        "behosh",
        "बेहोश",
        "conscious",
        "chakkar",
        "चक्कर",
    ),
    "one_sided_weakness": (
        "weak",
        "numb",
        "paraly",
        "kamzor",
        "kamjor",
        "कमज़ोर",
        "कमजोर",
        "लकवा",
        "सुन्न",
    ),
    "speech_difficulty": ("speech", "speak", "slur", "bol", "बोल", "जुबान", "आवाज़"),
    "pregnancy_possible": BODY["pregnan"],
}

PLACEHOLDERS = {
    "",
    "none",
    "no",
    "nil",
    "null",
    "unknown",
    "not specified",
    "not mentioned",
    "n/a",
    "na",
    "nahi",
    "नहीं",
    "koi nahi",
    "कोई नहीं",
    "unspecified",
}


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[\s,।॥.!?|;:()\-]+", text.lower()) if t]


def numbers_in(text: str) -> set[int]:
    """Every number the text carries, as digits or as a word in any table we know."""

    found = {int(d) for d in re.findall(r"\d{1,3}", text)}
    for token in _tokens(text):
        if token in NUMBERS:
            found.add(NUMBERS[token])
            continue
        # The recogniser glues repeated or clipped words: "दोदो दी से" for "दो दिन से". A
        # number word at the start of a token still counts. Prefix only, and only words of
        # two or more characters, so "दस्त" (loose motions) does read as "दस" - an accepted
        # cost; the LLM would have to invent "ten days" on top of it for that to matter.
        found.update(v for w, v in NUMBERS.items() if len(w) >= 2 and token.startswith(w))
    return found


def _mentions(text: str, aliases: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(alias in lowered for alias in aliases)


def grounded_duration(value: str | None, transcript: str) -> str | None:
    if value is None:
        return None
    said = numbers_in(transcript)
    claimed = numbers_in(value)
    if claimed:
        return value if claimed & said else None
    # No number in the value ("since yesterday", "a week"): the phrase itself must be there.
    if _mentions(value, YESTERDAY) and _mentions(transcript, YESTERDAY):
        return value
    lowered = transcript.lower()
    if any(len(w) >= 4 and w in lowered for w in _tokens(value)):
        return value
    return None


def grounded_age(value: int | None, transcript: str) -> int | None:
    if value is None:
        return None
    return value if value in numbers_in(transcript) else None


def grounded_complaint(value: str | None, transcript: str) -> str | None:
    """The complaint must name something the patient mentioned, in any script."""

    if value is None:
        return None
    lowered_value = value.lower()
    keyed = [
        key
        for key, aliases in BODY.items()
        if key in lowered_value or _mentions(lowered_value, aliases)
    ]
    if keyed:
        return value if any(_mentions(transcript, BODY[key]) for key in keyed) else None
    # Nothing we know: the model's own words must appear literally ("ankle hurts" -> "ankle pain").
    lowered = transcript.lower()
    content = [w for w in _tokens(value) if len(w) >= 4 and w not in {"pain", "ache", "problem"}]
    return value if any(w in lowered for w in content) else None


def grounded_list(values: list[str], transcript: str) -> list[str]:
    lowered = transcript.lower()
    kept = []
    for item in values:
        name = (item or "").strip()
        if name.lower() in PLACEHOLDERS or len(name) < 3:
            continue
        if name.lower() in lowered and name not in kept:
            kept.append(name)
    return kept


def ground(update: ClinicalUpdate, transcript: str) -> ClinicalUpdate:
    """Return a copy of `update` with everything the transcript does not support set to None."""

    grounded = update.model_copy(deep=True)
    grounded.complaint = grounded_complaint(update.complaint, transcript)
    grounded.duration = grounded_duration(update.duration, transcript)
    grounded.age_years = grounded_age(update.age_years, transcript)
    for field, aliases in SYMPTOMS.items():
        if getattr(update, field) is not None and not _mentions(transcript, aliases):
            setattr(grounded, field, None)
    grounded.medications = grounded_list(update.medications, transcript)
    grounded.allergies = grounded_list(update.allergies, transcript)
    return grounded
