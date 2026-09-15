#!/usr/bin/env python3
"""Which whisper.cpp setting is costing Hindi accuracy, as a number per setting.

`benchmark_languages.py` measures one configuration. This sweeps several and puts
their CER side by side, because "Hindi is bad" is not a thing anyone can fix and
"audio-ctx 750 costs 14 CER points on Hindi and 1 on English" is.

Run it **on the Jetson**, with the kiosk's own whisper server stopped — this
script starts and stops its own on a spare port so it can vary the flags the
service file fixes at boot:

    systemctl --user stop medikiosk-whisper
    python3 scripts/sweep_stt_config.py --languages hi en
    systemctl --user start medikiosk-whisper

Four things are worth suspecting before anything else, and each is a row here.

**`--audio-ctx 750`.** `run_whisper_server.sh` shrinks the encoder's audio
context from the full 1500 to halve latency, and its own comment records that
500 "began corrupting words". That cliff was found in English. Non-Latin script
degrades earlier, and the failure is not a rougher transcript — it is Devanagari
giving way to romanisation, which is a different sentence.

**`q5_0` quantisation.** Quantisation costs more on the multilingual decoder's
non-Latin vocabulary than it does on English.

**`large-v3-turbo`.** Turbo is a distilled decoder — four layers instead of
thirty-two. It keeps English quality and gives some of it back on lower-resource
languages; Hindi is one of them.

**No initial prompt.** whisper.cpp takes `--prompt`, and a few words of
Devanagari bias the decoder towards writing Devanagari at all.

Absolute numbers here are an upper bound: the clips are synthesised by the
kiosk's own TTS, which is cleaner than a patient in an OPD. The *comparison*
between two rows on identical clips is the part that carries.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))


@dataclass(frozen=True)
class Config:
    """One whisper-server configuration, and why it is in the sweep."""

    name: str
    why: str
    model: str | None = None
    audio_ctx: int | None = None
    beam_size: int | None = None
    prompt: str | None = None


#: A few words of ordinary clinical Hindi. Not a phrase the patient will say —
#: a prompt whose job is to tell the decoder which script this is going to be.
HINDI_PROMPT = "रोगी ने कहा कि उन्हें बुखार, खांसी और सिर में दर्द है।"

SWEEP: tuple[Config, ...] = (
    Config(
        "baseline",
        "exactly what run_whisper_server.sh ships today",
        audio_ctx=750,
    ),
    Config(
        "full-audio-ctx",
        "the one knob the script already admits corrupts words",
        audio_ctx=1500,
    ),
    Config(
        "full-ctx+prompt",
        "and a Devanagari prompt, which biases the script choice",
        audio_ctx=1500,
        prompt=HINDI_PROMPT,
    ),
    Config(
        "full-ctx+beam5",
        "greedy decoding is a latency choice; this prices it",
        audio_ctx=1500,
        beam_size=5,
    ),
)


def _server_flags(config: Config, model: Path, port: int, threads: int) -> list[str]:
    flags = [
        "--model",
        str(model),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--threads",
        str(threads),
        "--language",
        "auto",
        "--no-timestamps",
    ]
    if config.audio_ctx is not None:
        flags += ["--audio-ctx", str(config.audio_ctx)]
    if config.beam_size is not None:
        flags += ["--beam-size", str(config.beam_size)]
    if config.prompt is not None:
        flags += ["--prompt", config.prompt]
    return flags


def _wait_for(port: int, timeout: float) -> bool:
    """The model takes a while to load; a connection refused is not a failure yet."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(f"http://127.0.0.1:{port}/", method="GET")
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status < 500
        except urllib.error.HTTPError:
            return True
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(1.0)
    return False


def _measure(
    port: int, languages: list[str], clips: int, seed: int
) -> dict[str, tuple[float, float, float]]:
    """CER, WER and mean inference seconds per language, on this server.

    Reuses `benchmark_languages`' own synthesis and scoring rather than
    reimplementing them: two error-rate functions that disagree would make every
    row in the table incomparable with the numbers already in the repo.
    """
    sys.path.insert(0, str(REPO / "scripts"))
    from benchmark_languages import (  # type: ignore[import-not-found]  # noqa: PLC0415
        PHRASES,
        corpus_phrases,
        error_rates,
        resample_to_16k,
    )

    from medikiosk.config import Settings  # noqa: PLC0415
    from medikiosk.providers.voices import VoiceBank  # noqa: PLC0415
    from medikiosk.providers.whisper_provider import WhisperCppSTT  # noqa: PLC0415

    settings = Settings()
    voices = VoiceBank(
        REPO / settings.piper_binary,
        REPO / settings.voice_dir,
        settings.flite_binary,
        settings.flite_voice_dir,
        REPO / settings.prerendered_audio_dir,
    )
    whisper = WhisperCppSTT(f"http://127.0.0.1:{port}")

    out: dict[str, tuple[float, float, float]] = {}
    for language in languages:
        if not voices.available(language):
            continue
        phrases = list(PHRASES.get(language, ()))
        phrases += [text for _kind, text in corpus_phrases(language, clips, seed)]
        cers: list[float] = []
        wers: list[float] = []
        elapsed: list[float] = []
        for reference in phrases:
            audio = resample_to_16k(voices.synthesize(reference, language))
            started = time.monotonic()
            # Pinned, not auto-detected: every turn after the first is pinned in
            # the kiosk, and that is the shape worth measuring.
            heard, _detected = whisper.transcribe(audio, language)
            elapsed.append(time.monotonic() - started)
            cer, wer = error_rates(reference, heard)
            cers.append(cer)
            wers.append(wer)
        if cers:
            out[language] = (
                sum(cers) / len(cers),
                sum(wers) / len(wers),
                sum(elapsed) / len(elapsed),
            )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        type=Path,
        default=REPO / "offline/jetson/models/ggml-large-v3-turbo-q5_0.bin",
        help="the checkpoint every row uses unless it names its own",
    )
    parser.add_argument(
        "--binary",
        type=Path,
        default=REPO / "offline/jetson/src/whisper.cpp/build/bin/whisper-server",
    )
    parser.add_argument("--port", type=int, default=11599, help="a spare port, not the kiosk's")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--languages", nargs="+", default=["hi", "en"])
    parser.add_argument("--clips", type=int, default=8, help="corpus sentences per language")
    parser.add_argument("--seed", type=int, default=20260907)
    parser.add_argument("--load-timeout", type=float, default=180.0)
    args = parser.parse_args()

    if not args.binary.exists():
        print(f"whisper-server not built at {args.binary}", file=sys.stderr)
        return 1

    results: dict[str, dict[str, tuple[float, float, float]]] = {}
    for config in SWEEP:
        model = Path(config.model) if config.model else args.model
        if not model.exists():
            print(f"{config.name:18} SKIPPED — no model at {model}")
            continue

        print(f"\n==> {config.name}: {config.why}", flush=True)
        process = subprocess.Popen(  # noqa: S603 - flags are built above, not user input
            [str(args.binary), *_server_flags(config, model, args.port, args.threads)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            if not _wait_for(args.port, args.load_timeout):
                print(f"{config.name:18} SKIPPED — server never came up")
                continue
            results[config.name] = _measure(
                args.port, list(args.languages), args.clips, args.seed
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()

    # One table, because the comparison is the point and a wall of per-clip
    # output buries it.
    print(f"\n{'config':18} {'lang':5} {'CER':>7} {'WER':>7} {'sec/turn':>9}")
    print("-" * 50)
    for name, per_language in results.items():
        for language, (cer, wer, seconds) in per_language.items():
            print(f"{name:18} {language:5} {cer:7.2f} {wer:7.2f} {seconds:9.2f}")

    print(
        "\nRead the Hindi rows against the English ones. A change that moves "
        "Hindi and leaves English alone is the setting that was costing Hindi; "
        "a change that moves both is just a better decode."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
