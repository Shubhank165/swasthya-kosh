#!/usr/bin/env python3
"""Round-trip every supported language through the offline voice and the offline ASR.

For each language it synthesizes a known clinical phrase with the kiosk's own voice, sends the
audio to whisper.cpp, and reports what came back, which language Whisper thought it was, how long
inference took, and how far the transcript drifted from the text that was spoken.

Because the text is known, the drift is measurable: CER and WER against the reference turn "does
Tamil work?" into a number, which is what makes two ASR models comparable on the same clips.

--corpus draws from the real pre-rendered prompt set instead of the two built-in phrases, so the
sample is the questions patients are actually asked rather than a pair of stock sentences.

This measures the pipeline, not the patients: synthetic speech is cleaner and more regular than a
person in an OPD, so treat the absolute numbers as an upper bound and still run the human test.
The comparison between two ASR models on identical clips is the part that carries over.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from medikiosk.config import Settings  # noqa: E402
from medikiosk.edge.runtime import pcm_to_wav  # noqa: E402
from medikiosk.kiosk.prompts import spoken_prompts  # noqa: E402
from medikiosk.languages import LANGUAGES  # noqa: E402
from medikiosk.providers.voices import VoiceBank  # noqa: E402
from medikiosk.providers.whisper_provider import WhisperCppSTT  # noqa: E402

# One complaint and one bare yes per language: the two utterance shapes the kiosk depends on.
PHRASES: dict[str, tuple[str, str]] = {
    "hi": ("सीने में दर्द दो दिन से", "हाँ"),
    "en": ("chest pain for two days", "yes"),
    "bn": ("বুকে ব্যথা দুই দিন ধরে", "হ্যাঁ"),
    "mr": ("छातीत दुखणे दोन दिवसांपासून", "हो"),
    "te": ("ఛాతీ నొప్పి రెండు రోజుల నుండి", "అవును"),
    "ta": ("மார்பு வலி இரண்டு நாட்களாக", "ஆம்"),
    "gu": ("છાતીમાં દુખાવો બે દિવસથી", "હા"),
    "kn": ("ಎದೆ ನೋವು ಎರಡು ದಿನಗಳಿಂದ", "ಹೌದು"),
    "pa": ("ਛਾਤੀ ਵਿੱਚ ਦਰਦ ਦੋ ਦਿਨਾਂ ਤੋਂ", "ਹਾਂ"),
}


def resample_to_16k(wav_bytes: bytes) -> bytes:
    """Piper emits 22.05 kHz; whisper.cpp wants 16 kHz mono."""

    import audioop
    import io
    import wave

    with wave.open(io.BytesIO(wav_bytes)) as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        pcm = handle.readframes(handle.getnframes())
    if channels > 1:
        pcm = audioop.tomono(pcm, 2, 0.5, 0.5)
    if rate != 16000:
        pcm, _ = audioop.ratecv(pcm, 2, 1, rate, 16000, None)
    return pcm_to_wav(pcm)


def _normalize(text: str) -> str:
    """Strip what a transcript is not expected to reproduce: case, punctuation, spacing.

    Whisper punctuates and the reference text does too, but not identically, and a comma is not
    an ASR error worth counting. Unicode is normalized to NFC first so the same Devanagari
    grapheme composed two ways compares equal.
    """

    text = unicodedata.normalize("NFC", text)
    kept = [c for c in text if not unicodedata.category(c).startswith("P")]
    return " ".join("".join(kept).lower().split())


def _edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    """Levenshtein distance over whatever units are passed - characters or words."""

    previous = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, start=1):
        current = [i]
        for j, hyp in enumerate(hypothesis, start=1):
            current.append(
                previous[j - 1] if ref == hyp
                else 1 + min(previous[j - 1], previous[j], current[j - 1])
            )
        previous = current
    return previous[-1]


def error_rates(reference: str, hypothesis: str) -> tuple[float, float]:
    """(CER, WER) of a transcript against the text that was actually spoken.

    CER carries the comparison for Indic languages: their orthography and Whisper's tokenizer
    disagree about where a word ends, so WER can read as 1.0 while the transcript is nearly
    right. A rate above 1.0 (hallucinated text longer than the reference) is clipped, since
    "worse than everything" needs no further resolution.
    """

    ref, hyp = _normalize(reference), _normalize(hypothesis)
    if not ref:
        return (0.0, 0.0) if not hyp else (1.0, 1.0)
    cer = _edit_distance(list(ref), list(hyp)) / len(ref)
    ref_words, hyp_words = ref.split(), hyp.split()
    wer = _edit_distance(ref_words, hyp_words) / len(ref_words)
    return min(cer, 1.0), min(wer, 1.0)


def corpus_phrases(language: str, count: int, seed: int) -> list[tuple[str, str]]:
    """(kind, text) drawn from the real pre-rendered prompt set for this language.

    Sampled with a fixed seed so two ASR models are compared on identical clips rather than on
    whichever sentences each run happened to pick.
    """

    pool = sorted(
        p.text
        for p in spoken_prompts()
        if p.language == language and p.voice_language == language
    )
    picked = random.Random(seed).sample(pool, min(count, len(pool)))
    return [(f"corpus{i + 1}", text) for i, text in enumerate(picked)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure the offline TTS -> ASR round trip.")
    parser.add_argument(
        "--corpus",
        type=int,
        default=0,
        metavar="N",
        help="also run N sentences per language drawn from the real pre-rendered prompt set",
    )
    parser.add_argument("--seed", type=int, default=20260907, help="corpus sampling seed")
    args = parser.parse_args()

    settings = Settings()
    voices = VoiceBank(
        REPO / settings.piper_binary,
        REPO / settings.voice_dir,
        settings.flite_binary,
        settings.flite_voice_dir,
        REPO / settings.prerendered_audio_dir,
    )
    whisper = WhisperCppSTT(settings.whisper_url)
    if not whisper.health():
        print(f"whisper.cpp server not reachable at {settings.whisper_url}")
        return 1

    header = (
        f"{'lang':5} {'engine':6} {'kind':9} {'tts_ms':>7} {'asr_ms':>7} "
        f"{'CER':>5} {'WER':>5} {'heard':6}  text"
    )
    print(header)
    print("-" * len(header))
    failures = 0
    rates: dict[str, list[tuple[float, float]]] = {}
    for code, spec in LANGUAGES.items():
        if not voices.available(code):
            print(f"{code:5} {spec.engine:6} {'-':9} NO VOICE INSTALLED")
            failures += 1
            continue
        phrases = list(zip(("complaint", "yes"), PHRASES[code], strict=True))
        phrases += corpus_phrases(code, args.corpus, args.seed)
        for kind, phrase in phrases:
            started = time.monotonic()
            audio = resample_to_16k(voices.synthesize(phrase, code))
            tts_ms = round((time.monotonic() - started) * 1000)

            # Turn one runs auto-detect; every later turn is pinned to the locked language, which
            # is both faster and more accurate, so measure the shape the kiosk actually uses.
            pin = None if kind == "complaint" else code
            started = time.monotonic()
            text, detected = whisper.transcribe(audio, pin)
            asr_ms = round((time.monotonic() - started) * 1000)
            if pin is not None:
                detected = detected or code

            cer, wer = error_rates(phrase, text)
            rates.setdefault(code, []).append((cer, wer))

            flag = "" if detected == code else f"  <- expected {code}"
            print(
                f"{code:5} {spec.engine:6} {kind:9} {tts_ms:7} {asr_ms:7} "
                f"{cer:5.2f} {wer:5.2f} {str(detected):6}  {text!r}{flag}"
            )
            if detected != code:
                failures += 1

    # The per-language means are the comparable number: run this against two ASR models and the
    # one with lower CER on the same clips is the better model for this kiosk.
    print(f"\n{'lang':5} {'clips':>5} {'CER':>6} {'WER':>6}")
    everything: list[tuple[float, float]] = []
    for code, measured in rates.items():
        everything += measured
        mean_cer = sum(c for c, _ in measured) / len(measured)
        mean_wer = sum(w for _, w in measured) / len(measured)
        print(f"{code:5} {len(measured):5} {mean_cer:6.2f} {mean_wer:6.2f}")
    if everything:
        print(
            f"{'ALL':5} {len(everything):5} "
            f"{sum(c for c, _ in everything) / len(everything):6.2f} "
            f"{sum(w for _, w in everything) / len(everything):6.2f}"
        )
    print(f"\nlanguage detection mismatches: {failures}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
