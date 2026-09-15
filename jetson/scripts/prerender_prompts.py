#!/usr/bin/env python3
"""Render every fixed kiosk prompt to WAV, once, with the best voice each language has.

Run on the Jetson (it needs the Piper binary and voices), with network access the first time so
the MMS-TTS checkpoints can be fetched:

    offline/jetson/audio-venv/bin/python scripts/prerender_prompts.py

Why this exists: Piper can only voice hi/en/te on this board - its bn/mr voices carry
multi-codepoint diphthongs ("aɪ") that the archived 2023 binary refuses to load, and it has no
ta/gu/kn/pa voice at all - which left six of nine languages on Flite, whose 2005-era diphone
synthesis is what patients called robotic. MMS-TTS is a neural VITS voice per language and sounds
far better, but six more resident models do not fit an 8 GB board next to Whisper and gemma. Since
the spoken corpus is closed (see medikiosk.kiosk.prompts), rendering it ahead of time buys the
quality without the runtime cost.

Re-runnable: an already-rendered prompt is skipped, so a new question costs only its own audio.
"""

from __future__ import annotations

import argparse
import io
import sys
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from medikiosk.config import get_settings  # noqa: E402
from medikiosk.kiosk.prompts import Prompt, spoken_prompts  # noqa: E402
from medikiosk.languages import LANGUAGES  # noqa: E402
from medikiosk.providers.local_tts import PiperTTS  # noqa: E402
from medikiosk.providers.voices import cache_name  # noqa: E402

# Languages whose Piper voice actually loads on this board. Everything else is rendered by MMS.
PIPER_LANGUAGES = ("hi", "en", "te")

# MMS-TTS is published per language under an ISO 639-3 code. All six here are native-script
# (is_uroman false in their tokenizer config), so no romanization step is needed.
MMS_MODELS = {
    "bn": "facebook/mms-tts-ben",
    "mr": "facebook/mms-tts-mar",
    "ta": "facebook/mms-tts-tam",
    "gu": "facebook/mms-tts-guj",
    "kn": "facebook/mms-tts-kan",
    "pa": "facebook/mms-tts-pan",
}


class MmsVoice:
    """One MMS-TTS VITS voice, loaded on first use and kept for the rest of the run."""

    def __init__(self, model_id: str) -> None:
        import torch
        from transformers import AutoTokenizer, VitsModel

        self.torch = torch
        self.model = VitsModel.from_pretrained(model_id)
        self.model.eval()
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.rate = int(self.model.config.sampling_rate)

    def synthesize(self, text: str) -> bytes:
        inputs = self.tokenizer(text, return_tensors="pt")
        with self.torch.no_grad():
            waveform = self.model(**inputs).waveform[0]
        # VITS emits float in [-1, 1]; clamp before scaling so a hot sample wraps to full scale
        # instead of overflowing into the opposite sign and clicking.
        clamped = self.torch.clamp(waveform, -1.0, 1.0)
        pcm = (clamped * 32767.0).to(self.torch.int16).cpu().numpy().tobytes()
        return _wav(pcm, self.rate)


def _wav(pcm: bytes, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


def _engine_for(language: str, settings) -> object:
    if language in PIPER_LANGUAGES:
        from medikiosk.languages import profile

        voice = Path(settings.voice_dir) / profile(language).voice
        if not voice.exists():
            raise SystemExit(f"Piper voice missing for {language}: {voice}")
        return PiperTTS(settings.piper_binary, voice)
    if language in MMS_MODELS:
        return MmsVoice(MMS_MODELS[language])
    raise SystemExit(f"No pre-render engine defined for {language!r}")


def render(prompts: list[Prompt], out_dir: Path, force: bool) -> tuple[int, int, int]:
    settings = get_settings()
    engines: dict[str, object] = {}
    # The same English sentence is keyed under every language that lacks a translation. Render it
    # once and write the bytes to each key rather than synthesizing it seven times.
    rendered: dict[tuple[str, str], bytes] = {}
    written = skipped = failed = 0

    for prompt in prompts:
        path = out_dir / prompt.language / cache_name(prompt.text, prompt.language)
        if path.exists() and not force:
            skipped += 1
            continue
        key = (prompt.voice_language, prompt.text)
        audio = rendered.get(key)
        if audio is None:
            engine = engines.get(prompt.voice_language)
            if engine is None:
                print(f"loading voice: {prompt.voice_language}", flush=True)
                engine = _engine_for(prompt.voice_language, settings)
                engines[prompt.voice_language] = engine
            try:
                audio = engine.synthesize(prompt.text)  # type: ignore[attr-defined]
            except Exception as error:
                # One bad prompt must not abandon the other 350; the runtime still has a live
                # engine to fall back on for whatever failed here.
                print(f"FAILED {prompt.language} {prompt.source}: {error}", flush=True)
                failed += 1
                continue
            rendered[key] = audio
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        written += 1
        if written % 25 == 0:
            print(f"  {written} rendered", flush=True)
    return written, skipped, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO / "offline" / "audio")
    parser.add_argument("--languages", nargs="*", default=list(LANGUAGES))
    parser.add_argument("--force", action="store_true", help="re-render prompts already on disk")
    args = parser.parse_args()

    wanted = set(args.languages)
    prompts = [p for p in spoken_prompts() if p.language in wanted]
    print(f"{len(prompts)} prompts, {len(wanted)} languages -> {args.out}", flush=True)

    written, skipped, failed = render(prompts, args.out, args.force)
    print(f"done: {written} written, {skipped} already present, {failed} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
