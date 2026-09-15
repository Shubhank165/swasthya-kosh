"""Which languages the offline kiosk supports, and what speaks each one.

Adding a language means four things, all of which must be present or the language is not offered:
a Whisper language code, a TTS voice, translated questions and prompts, and the yes/no and number
words for that language. A language with a voice but no translations is worse than no support: the
kiosk would speak English text through an Indic voice.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageProfile:
    code: str
    native_name: str
    engine: str  # "piper" or "flite"
    voice: str  # Piper .onnx filename, or Flite .flitevox filename
    # Flite's Indic voices are pitched high and read fast for clinical prompts.
    duration_stretch: float = 1.0


# Piper (neural) wherever a voice exists; Flite CMU Indic for the rest.
LANGUAGES: dict[str, LanguageProfile] = {
    "hi": LanguageProfile("hi", "हिन्दी", "piper", "hi_IN-pratham-medium.onnx"),
    "en": LanguageProfile("en", "English", "piper", "en_US-lessac-medium.onnx"),
    # bn/mr Piper voices need a newer phoneme map than the shipped binary understands
    # ("aɪ is not a single codepoint"), so they use Flite until Piper is upgraded.
    "bn": LanguageProfile("bn", "বাংলা", "flite", "cmu_indic_ben_rm.flitevox", 1.15),
    "mr": LanguageProfile("mr", "मराठी", "flite", "cmu_indic_mar_aup.flitevox", 1.15),
    "te": LanguageProfile("te", "తెలుగు", "piper", "te_IN-maya-medium.onnx"),
    "ta": LanguageProfile("ta", "தமிழ்", "flite", "cmu_indic_tam_sdr.flitevox", 1.15),
    "gu": LanguageProfile("gu", "ગુજરાતી", "flite", "cmu_indic_guj_ad.flitevox", 1.15),
    "kn": LanguageProfile("kn", "ಕನ್ನಡ", "flite", "cmu_indic_kan_plv.flitevox", 1.15),
    "pa": LanguageProfile("pa", "ਪੰਜਾਬੀ", "flite", "cmu_indic_pan_amp.flitevox", 1.15),
}

DEFAULT_LANGUAGE = "hi"


def profile(code: str) -> LanguageProfile:
    try:
        return LANGUAGES[code]
    except KeyError:
        raise ValueError(f"Unsupported language {code!r}; expected {sorted(LANGUAGES)}") from None
