"""The pre-rendered prompt cache: it must hit for what was rendered, and never fake a hit."""

from __future__ import annotations

import io
import wave

import pytest

from medikiosk.kiosk.flow import SCREEN_TEXT
from medikiosk.kiosk.prompts import spoken_prompts
from medikiosk.languages import LANGUAGES
from medikiosk.providers.voices import VoiceBank, cache_name, normalize

NOWHERE = "nowhere"


def bank(tmp_path, prerendered=True):
    """A VoiceBank whose live engines cannot possibly work.

    Any call that reaches Piper or Flite raises, so a passing lookup test proves the audio came
    from the cache rather than from a binary that happened to be installed on this machine.
    """

    return VoiceBank(
        f"{NOWHERE}/piper",
        NOWHERE,
        f"{NOWHERE}/flite",
        NOWHERE,
        tmp_path if prerendered else None,
    )


def write_cached(tmp_path, text: str, language: str, payload: bytes) -> None:
    path = tmp_path / language / cache_name(text, language)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def test_cached_prompt_is_returned_without_touching_an_engine(tmp_path):
    write_cached(tmp_path, "आपको क्या तकलीफ़ है?", "hi", b"RIFFcached")
    assert bank(tmp_path).synthesize("आपको क्या तकलीफ़ है?", "hi") == b"RIFFcached"


def test_whitespace_differences_still_hit_the_cache(tmp_path):
    write_cached(tmp_path, "how long has this been going on?", "en", b"RIFFcached")
    assert bank(tmp_path).synthesize("how long   has this\nbeen going on?", "en") == b"RIFFcached"


def test_cache_is_keyed_by_language(tmp_path):
    """The same sentence in two languages is two recordings, never one shared file."""

    write_cached(tmp_path, "Skip", "en", b"RIFFenglish")
    assert cache_name("Skip", "en") != cache_name("Skip", "ta")
    with pytest.raises((FileNotFoundError, OSError)):
        bank(tmp_path).synthesize("Skip", "ta")


def test_miss_falls_through_to_the_live_engine(tmp_path):
    """A prompt nobody rendered must be synthesized, not silently returned as empty audio."""

    with pytest.raises((FileNotFoundError, OSError)):
        bank(tmp_path).synthesize("something nobody rendered", "hi")


def test_cache_does_not_make_a_language_look_available(tmp_path):
    """Rendered audio covers the fixed prompts only, so it must not mask a missing engine.

    Reporting Tamil as available on the strength of the cache would get a patient through every
    scripted line and then fail on the first sentence nobody rendered, mid-interview.
    """

    write_cached(tmp_path, "வணக்கம்", "ta", b"RIFFcached")
    assert bank(tmp_path).available("ta") is False


def test_no_prerender_directory_behaves_as_before(tmp_path):
    assert bank(tmp_path, prerendered=False).prerendered("anything", "hi") is None


def test_unreadable_cache_entry_degrades_to_live_synthesis(tmp_path):
    """A directory where a WAV should be is corruption, not a reason to go silent."""

    path = tmp_path / "hi" / cache_name("blocked", "hi")
    path.mkdir(parents=True)
    assert bank(tmp_path).prerendered("blocked", "hi") is None


def test_normalize_is_what_the_key_is_built_from():
    assert normalize("  a \n b  ") == "a b"
    assert cache_name("  a \n b  ", "hi") == cache_name("a b", "hi")


# ------------------------------------------------------------------ the corpus itself


def test_every_language_has_prompts():
    by_language = {p.language for p in spoken_prompts()}
    assert by_language == set(LANGUAGES)


def test_prompts_are_unique_per_language_and_text():
    prompts = spoken_prompts()
    keys = [(p.language, p.text) for p in prompts]
    assert len(keys) == len(set(keys))


# The two corpora that are not translated into all nine languages: screen text (English and Hindi
# in flow.SCREEN_TEXT) and the Prakriti form (English and Hindi on the CCRAS form itself).
PARTLY_TRANSLATED = ("screen:", "prakriti:")


def test_untranslated_text_is_spoken_by_the_english_voice():
    """Where there is no translation the kiosk shows the English sentence.

    Reading English orthography with a Tamil voice is barely intelligible; the render step is
    where that pairing gets fixed, so the fallback is rendered in the English voice instead.
    """

    mismatched = [p for p in spoken_prompts() if p.voice_language != p.language]
    assert mismatched, "expected at least the untranslated screen text"
    assert all(p.voice_language == "en" for p in mismatched)
    assert all(p.source.startswith(PARTLY_TRANSLATED) for p in mismatched)


def test_fully_translated_text_is_spoken_by_its_own_voice():
    translated = [
        p for p in spoken_prompts() if not p.source.startswith(PARTLY_TRANSLATED)
    ]
    assert translated
    assert all(p.voice_language == p.language for p in translated)


def test_hindi_prakriti_is_spoken_in_hindi():
    """Hindi is on the form, so it must not fall back to the English voice."""

    hindi = [
        p for p in spoken_prompts() if p.language == "hi" and p.source.startswith("prakriti:")
    ]
    assert hindi
    assert all(p.voice_language == "hi" for p in hindi)


def test_screen_text_uses_the_translation_where_one_exists():
    hindi = {p.text for p in spoken_prompts() if p.language == "hi" and p.source == "screen:skip"}
    assert hindi == {SCREEN_TEXT["skip"]["hi"]}


def test_a_rendered_corpus_answers_every_prompt(tmp_path):
    """End to end: render placeholder audio for the whole corpus, then ask VoiceBank for each line.

    This is the check that keeps the renderer and the runtime keyed the same way. If either side
    changes how it normalizes or hashes, every lookup here misses and the live engines raise.
    """

    prompts = spoken_prompts()
    for prompt in prompts:
        write_cached(tmp_path, prompt.text, prompt.language, _silence())

    voices = bank(tmp_path)
    for prompt in prompts:
        audio = voices.synthesize(prompt.text, prompt.language)
        with wave.open(io.BytesIO(audio)) as handle:
            assert handle.getnchannels() == 1


def _silence() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 160)
    return buffer.getvalue()
