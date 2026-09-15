"""Every line the kiosk speaks that is known before a patient walks up.

In the offline profile the spoken corpus is closed: the clinical questions come from a fixed
table, the interviewer prompts come from another, the Ayurveda questions from a third, and the
screen text from a fourth. Nothing the patient says changes the wording -
TemplateQuestionNaturalizer returns the template verbatim. So the audio can all be rendered
ahead of time, which is what lets the six languages Piper cannot voice sound like the three it
can.

This module is the single definition of that corpus. tools/prerender_prompts.py renders exactly
what it lists and VoiceBank looks up exactly what it keys, so a prompt cannot be added in one place
and silently missed in the other - test_prompts.py asserts the two agree.
"""

from __future__ import annotations

from dataclasses import dataclass

from medikiosk.clinical.translations import PROMPT_TEXT, QUESTION_TEXT
from medikiosk.kiosk import ayurveda, prakriti
from medikiosk.kiosk.flow import SCREEN_TEXT
from medikiosk.languages import LANGUAGES


@dataclass(frozen=True)
class Prompt:
    """One line to render.

    `language` is what the runtime will ask for; `voice_language` is what should say it. They differ
    only where a string has no translation: flow.text() hands a Tamil session the English sentence,
    and an English sentence read by a Tamil voice is less intelligible than one read by the English
    voice. Rendering ahead of time is the first chance to get that pairing right.
    """

    language: str
    text: str
    voice_language: str
    source: str


def spoken_prompts() -> list[Prompt]:
    """Every (language, text) pair VoiceBank can be asked for during an offline session."""

    prompts: list[Prompt] = []
    seen: set[tuple[str, str]] = set()

    def add(language: str, text: str, voice_language: str, source: str) -> None:
        text = " ".join(text.split())
        if not text or (language, text) in seen:
            return
        seen.add((language, text))
        prompts.append(Prompt(language, text, voice_language, source))

    for language in LANGUAGES:
        for key, table in QUESTION_TEXT.items():
            if language in table:
                add(language, table[language], language, f"question:{key}")
        for key, table in PROMPT_TEXT.items():
            if language in table:
                add(language, table[language], language, f"prompt:{key}")
        for question in ayurveda.QUESTIONS:
            if language in question.text:
                add(language, question.text[language], language, f"ayurveda:{question.id}")
        # Prakriti is printed on the CCRAS form in English and Hindi only, so every other language
        # is rendered from the English wording in the English voice - same rule as screen text.
        for item in prakriti.ITEMS:
            translated = language == "hi"
            add(
                language,
                item.hi if translated else item.en,
                language if translated else "en",
                f"prakriti:{item.id}",
            )
        for key, table in SCREEN_TEXT.items():
            # Untranslated screen text falls back to English wording, so it gets the English voice.
            translated = language in table
            add(
                language,
                table[language] if translated else table["en"],
                language if translated else "en",
                f"screen:{key}",
            )
    return prompts
