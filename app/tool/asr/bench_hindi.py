#!/usr/bin/env python3
"""What each candidate ASR model actually writes when a patient speaks Hindi.

DECISIONS §69 closed the Hindi microphone on a measurement, and it can only be
reopened on one. This runs every candidate over *identical* clips and scores
them the way `jetson/scripts/benchmark_languages.py` scores the kiosk, so a
number here and a number there mean the same thing.

    python3 tool/asr/bench_hindi.py                       # everything present
    python3 tool/asr/bench_hindi.py indicconformer-hi-int8

The clips are synthesised by a Piper Hindi voice: clean, evenly paced speech,
which is the friendliest input an ASR model ever gets. Treat every number as an
upper bound on a patient speaking into a phone in an OPD — the *comparison*
between two rows on the same clips is the part that carries, which is the same
caveat `benchmark_languages.py` carries.

Setup (build-time only; none of this ships):

    python3 -m venv .venv && .venv/bin/pip install sherpa-onnx numpy
    curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-hi_IN-pratham-medium.tar.bz2
    tar xf vits-piper-hi_IN-pratham-medium.tar.bz2
"""

from __future__ import annotations

import argparse
import time
import unicodedata
from pathlib import Path

import numpy as np
import sherpa_onnx

APP = Path(__file__).resolve().parent.parent.parent

#: Ordinary OPD answers, not tongue-twisters: a complaint, a duration, a
#: medicine, a bare yes. The bare yes is deliberate — it is the utterance a
#: yes/no question produces and the one every CTC model here gets wrong.
PHRASES = (
    "सीने में दर्द दो दिन से",
    "हाँ",
    "तीन दिनों से",
    "मुझे बुखार है",
    "दो दिन से खांसी है",
    "पेट में बहुत तेज़ दर्द हो रहा है",
    "मुझे चक्कर आ रहे हैं और कमजोरी लग रही है",
    "दवा खाने के बाद उल्टी हुई",
    "शुगर की दवा चल रही है",
    "सांस लेने में तकलीफ़ है",
)


def _normalize(text: str) -> str:
    """NFC, no punctuation, no case — the same normalisation the kiosk uses."""
    text = unicodedata.normalize("NFC", text)
    kept = "".join(c for c in text if not unicodedata.category(c).startswith("P"))
    return " ".join(kept.lower().split())


def _edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, start=1):
        current = [i]
        for j, hyp in enumerate(hypothesis, start=1):
            current.append(
                previous[j - 1]
                if ref == hyp
                else 1 + min(previous[j - 1], previous[j], current[j - 1])
            )
        previous = current
    return previous[-1]


def error_rates(reference: str, hypothesis: str) -> tuple[float, float]:
    """(CER, WER). CER carries the comparison: Devanagari word boundaries and a
    model's tokenizer disagree, so WER reads 1.0 while the sentence is right."""
    ref, hyp = _normalize(reference), _normalize(hypothesis)
    if not ref:
        return (0.0, 0.0)
    cer = _edit_distance(list(ref), list(hyp)) / len(ref)
    ref_words, hyp_words = ref.split(), hyp.split()
    wer = _edit_distance(ref_words, hyp_words) / len(ref_words)
    return min(cer, 1.0), min(wer, 1.0)


def _resample(samples: np.ndarray, source: int, target: int = 16000) -> np.ndarray:
    if source == target:
        return samples
    count = int(len(samples) * target / source)
    return np.interp(
        np.linspace(0, len(samples), count, endpoint=False),
        np.arange(len(samples)),
        samples,
    ).astype(np.float32)


def _clips(voice: Path) -> list[tuple[str, np.ndarray]]:
    tts = sherpa_onnx.OfflineTts(
        sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=str(voice / "hi_IN-pratham-medium.onnx"),
                    tokens=str(voice / "tokens.txt"),
                    data_dir=str(voice / "espeak-ng-data"),
                ),
                num_threads=2,
                provider="cpu",
            ),
            max_num_sentences=1,
        )
    )
    out = []
    for phrase in PHRASES:
        audio = tts.generate(phrase, sid=0, speed=1.0)
        samples = np.array(audio.samples, dtype=np.float32)
        out.append((phrase, _resample(samples, audio.sample_rate)))
    return out


def _whisper_tiny():
    """What the APK ships today — the baseline every other row argues against."""
    d = APP / "assets/asr/whisper-tiny"
    return sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=str(d / "tiny-encoder.int8.onnx"),
        decoder=str(d / "tiny-decoder.int8.onnx"),
        tokens=str(d / "tiny-tokens.txt"),
        language="hi",
        task="transcribe",
        num_threads=2,
    )


def _indic(directory: Path):
    """IndicConformer, built by build_indicconformer.py."""
    model = directory / "model.int8.onnx"
    if not model.exists():
        model = directory / "model.onnx"
    return sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
        model=str(model), tokens=str(directory / "tokens.txt"), num_threads=2
    )


def _dolphin(directory: Path):
    """The ready-made multilingual alternative. It writes Devanagari — and also
    writes Arabic and Japanese into the same sentence, because sherpa-onnx
    exposes no way to pin its language. Kept here so that stays measurable."""
    return sherpa_onnx.OfflineRecognizer.from_dolphin_ctc(
        model=str(directory / "model.int8.onnx"),
        tokens=str(directory / "tokens.txt"),
        num_threads=2,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", nargs="*", help="default: every one that is present")
    parser.add_argument("--voice", type=Path, default=Path("vits-piper-hi_IN-pratham-medium"))
    parser.add_argument("--indic", type=Path, default=APP / "assets/asr/indic-hi")
    parser.add_argument("--dolphin", type=Path, default=Path("sherpa-onnx-dolphin-base-ctc-multi-lang-int8-2025-04-02"))
    args = parser.parse_args()

    builders = {
        "whisper-tiny-int8": _whisper_tiny,
        "indicconformer-hi": lambda: _indic(args.indic),
        "dolphin-base-int8": lambda: _dolphin(args.dolphin),
    }
    wanted = args.candidates or list(builders)

    clips = _clips(args.voice)
    print(f"{len(clips)} synthesised Hindi clips\n")

    for name in wanted:
        try:
            recognizer = builders[name]()
        except Exception as error:  # noqa: BLE001 - a missing candidate is a skip
            print(f"===== {name}: SKIPPED — {error}\n")
            continue
        print(f"===== {name}")
        cers, wers, seconds = [], [], []
        for reference, audio in clips:
            stream = recognizer.create_stream()
            stream.accept_waveform(16000, audio)
            started = time.monotonic()
            recognizer.decode_stream(stream)
            seconds.append(time.monotonic() - started)
            heard = stream.result.text.strip()
            cer, wer = error_rates(reference, heard)
            cers.append(cer)
            wers.append(wer)
            print(f"  CER {cer:4.2f}  {reference}\n            -> {heard!r}")
        print(
            f"  MEAN CER {sum(cers)/len(cers):.2f}  WER {sum(wers)/len(wers):.2f}  "
            f"{sum(seconds)/len(seconds):.2f}s/clip\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
