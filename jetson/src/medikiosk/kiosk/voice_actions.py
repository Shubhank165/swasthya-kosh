"""Conservative local commands: only a complete phrase selects an action."""

from __future__ import annotations

import re
import unicodedata
from enum import Enum


class Decision(str, Enum):
    YES = "yes"
    NO = "no"
    UNCERTAIN = "uncertain"


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().strip()
    return " ".join(
        "".join(c if not unicodedata.category(c).startswith("P") else " " for c in text).split()
    )


YES = {
    "yes",
    "yes please",
    "that is correct",
    "haan",
    "han",
    "हाँ",
    "हां",
    "जी हाँ",
    "हो",
    "হ্যাঁ",
    "అవును",
    "ஆம்",
    "હા",
    "ಹೌದು",
    "ਹਾਂ",
}
NO = {
    "no",
    "no thanks",
    "nahi",
    "nahin",
    "नहीं",
    "नही",
    "না",
    "नाही",
    "కాదు",
    "இல்லை",
    "ના",
    "ಇಲ್ಲ",
    "ਨਹੀਂ",
}
ALIASES = {
    "repeat": {
        "repeat",
        "repeat please",
        "say again",
        "दोहराएं",
        "दोहराएँ",
        "फिर से",
        "আবার বলুন",
        "पुन्हा सांगा",
        "మళ్ళీ చెప్పండి",
        "மீண்டும் சொல்லுங்கள்",
        "ફરી કહો",
        "ಮತ್ತೆ ಹೇಳಿ",
        "ਦੁਬਾਰਾ ਦੱਸੋ",
    },
    "slower": {
        "slower",
        "speak slower",
        "धीरे बोलें",
        "ধীরে বলুন",
        "हळू बोला",
        "నెమ్మదిగా చెప్పండి",
        "மெதுவாக பேசுங்கள்",
        "ધીમે બોલો",
        "ನಿಧಾನವಾಗಿ ಹೇಳಿ",
        "ਹੌਲੀ ਬੋਲੋ",
    },
    "more_time": {
        "more time",
        "wait",
        "और समय",
        "रुकिए",
        "আরও সময়",
        "आणखी वेळ",
        "మరింత సమయం",
        "இன்னும் நேரம்",
        "વધુ સમય",
        "ಇನ್ನಷ್ಟು ಸಮಯ",
        "ਹੋਰ ਸਮਾਂ",
    },
    "back": {
        "back",
        "go back",
        "पीछे",
        "वापस",
        "পিছনে",
        "मागे",
        "వెనక్కి",
        "பின்னால்",
        "પાછળ",
        "ಹಿಂದೆ",
        "ਪਿੱਛੇ",
    },
    "cancel": {"cancel", "रद्द", "বাতিল", "రద్దు", "ரத்து", "રદ", "ರದ್ದು", "ਰੱਦ"},
    "help": {
        "help",
        "help me",
        "staff",
        "मदद",
        "सहायता",
        "সাহায্য",
        "मदत",
        "సహాయం",
        "உதவி",
        "મદદ",
        "ಸಹಾಯ",
        "ਮਦਦ",
    },
    "unknown": {
        "unknown",
        "i do not know",
        "i don't know",
        "not sure",
        "पता नहीं",
        "मालूम नहीं",
        "জানি না",
        "माहित नाही",
        "తెలియదు",
        "தெரியாது",
        "ખબર નથી",
        "ಗೊತ್ತಿಲ್ಲ",
        "ਪਤਾ ਨਹੀਂ",
    },
    "refuse": {
        "refuse",
        "prefer not to answer",
        "do not want to answer",
        "जवाब नहीं देना",
        "উত্তর দিতে চাই না",
        "उत्तर द्यायचे नाही",
        "సమాధానం చెప్పను",
        "பதில் சொல்ல விரும்பவில்லை",
        "જવાબ આપવો નથી",
        "ಉತ್ತರಿಸಲು ಇಷ್ಟವಿಲ್ಲ",
        "ਜਵਾਬ ਨਹੀਂ ਦੇਣਾ",
    },
    "skip": {"skip", "छोड़ें", "এড়িয়ে যান", "वगळा", "దాటవేయి", "தவிர்", "છોડો", "ಬಿಡಿ", "ਛੱਡੋ"},
    "confirm": {
        "confirm",
        "confirmed",
        "पुष्टि",
        "নিশ্চিত করুন",
        "पुष्टी",
        "నిర్ధారించండి",
        "உறுதி",
        "પુષ્ટિ",
        "ದೃಢಪಡಿಸಿ",
        "ਪੁਸ਼ਟੀ",
    },
    "restart": {
        "restart",
        "start again",
        "फिर से शुरू",
        "আবার শুরু",
        "पुन्हा सुरू",
        "మళ్ళీ ప్రారంభించు",
        "மீண்டும் தொடங்கு",
        "ફરી શરૂ",
        "ಮತ್ತೆ ಪ್ರಾರಂಭಿಸಿ",
        "ਦੁਬਾਰਾ ਸ਼ੁਰੂ",
    },
    "scan": {"scan", "scan document", "स्कैन", "স্ক্যান", "స్కాన్", "ஸ்கேன்", "સ્કેન", "ಸ್ಕ್ಯಾನ್", "ਸਕੈਨ"},
    "retake": {
        "retake",
        "take again",
        "फिर फोटो",
        "আবার ছবি",
        "पुन्हा फोटो",
        "మళ్ళీ ఫోటో",
        "மீண்டும் படம்",
        "ફરી ફોટો",
        "ಮತ್ತೆ ಫೋಟೋ",
        "ਦੁਬਾਰਾ ਫੋਟੋ",
    },
    "discard": {
        "discard",
        "remove photo",
        "फोटो हटाएं",
        "ছবি সরান",
        "फोटो काढा",
        "ఫోటో తొలగించు",
        "படத்தை நீக்கு",
        "ફોટો દૂર કરો",
        "ಫೋಟೋ ತೆಗೆದುಹಾಕಿ",
        "ਫੋਟੋ ਹਟਾਓ",
    },
    "keep": {"keep", "keep document", "रखें", "दस्तावेज़ रखें"},
    "withdraw": {"withdraw permission", "stop collection", "अनुमति वापस लें", "संग्रह रोकें"},
    "done": {
        "done",
        "finish",
        "पूरा",
        "হয়ে গেছে",
        "पूर्ण",
        "పూర్తయింది",
        "முடிந்தது",
        "પૂર્ણ",
        "ಮುಗಿದಿದೆ",
        "ਪੂਰਾ",
    },
}


def parse_age(text: str, language: str | None = None) -> int | None:
    """Exact age phrases only: reject ranges and unrelated numbers rather than adding them."""
    value = normalized(text)
    value = re.sub(r"^(?:i am|my age is|मेरी उम्र|मेरी आयु)\s+", "", value)
    value = re.sub(r"\s+(?:years? old|years?|साल है|वर्ष है|साल|वर्ष)$", "", value)
    if value.isdecimal():
        number = int(value)
        return number if 0 <= number <= 125 else None
    from medikiosk.clinical.answers import NUMBER_WORDS

    words = {**NUMBER_WORDS["en"], **NUMBER_WORDS.get((language or "en")[:2], {})}
    words.update(
        eleven=11,
        twelve=12,
        thirteen=13,
        fourteen=14,
        fifteen=15,
        sixteen=16,
        seventeen=17,
        eighteen=18,
        nineteen=19,
    )
    if value in words:
        return words[value]
    parts = value.split()
    if len(parts) == 2 and parts[0] in words and parts[1] in words:
        tens, unit = words[parts[0]], words[parts[1]]
        if tens >= 20 and tens % 10 == 0 and 0 < unit < 10:
            return tens + unit
    return None


def review_number(text: str) -> int | None:
    match = re.fullmatch(
        r"(?:edit(?: answer)?|change(?: answer)?|उत्तर)\s+(\d+)(?:\s+बदलें)?", normalized(text)
    )
    return int(match[1]) if match else None


def parse_decision(text: str, language: str | None = None) -> Decision:
    value = normalized(text)
    if value in {normalized(s) for s in YES}:
        return Decision.YES
    if value in {normalized(s) for s in NO}:
        return Decision.NO
    return Decision.UNCERTAIN


def parse_command(text: str, language: str | None = None) -> str | None:
    value = normalized(text)
    return next(
        (key for key, aliases in ALIASES.items() if value in {normalized(s) for s in aliases}), None
    )


def match_option(text: str, options: list[dict], language: str | None = None):
    value = normalized(text)
    # Unicode decimal digits, and the entire numeral, never a prefix search.
    number = re.fullmatch(
        r"(?:(?:option|number|विकल्प|क्रमांक|বিকল্প|ఎంపిక|விருப்பம்|વિકલ્પ|ಆಯ್ಕೆ|ਵਿਕਲਪ)\s+)?(\d+)", value
    )
    if number:
        index = int(number[1]) - 1
        return options[index]["value"] if 0 <= index < len(options) else None
    words = [
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
    ]
    for index, word in enumerate(words):
        if value in {word, f"option {word}"}:
            return options[index]["value"] if index < len(options) else None
    matches = []
    for option in options:
        aliases = [str(option["value"]), option.get("label", ""), *option.get("aliases", [])]
        if option["value"] == "yes":
            aliases.extend(YES)
        elif option["value"] == "no":
            aliases.extend(NO)
        if value and value in {normalized(a) for a in aliases}:
            matches.append(option["value"])
    return matches[0] if len(matches) == 1 else None
