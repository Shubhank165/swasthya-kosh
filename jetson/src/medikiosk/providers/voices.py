"""Picks the right offline voice for a language and keeps the engines around.

Three sources, in order. Pre-rendered audio first: every prompt the kiosk actually speaks in the
offline profile - the Dashavidha questions, the Ayurveda questions, the screen text - is a closed
set known at build time, so it is synthesized once by the best engine available for each language
and shipped as WAV. Piper (neural) second, for the languages it can voice live. Flite's CMU Indic
voices last.

The cache exists because live quality is not uniform: Piper can only voice hi/en/te here (its bn/mr
voices need a phoneme map the archived 2023 binary cannot load), which left six of nine languages
on Flite - 2005-era diphone concatenation that patients described as robotic. Rendering the fixed
prompts ahead of time with MMS-TTS lifts those six to neural quality without putting another model
in the 8 GB budget at runtime, and drops synthesis latency to a file read for every prompt a
patient normally hears.

Live engines stay wired up regardless, so text nobody pre-rendered still gets spoken.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from medikiosk.languages import LanguageProfile, profile
from medikiosk.providers.local_tts import FliteTTS, PiperTTS


def normalize(text: str) -> str:
    """Collapse whitespace, the one transform both the renderer and the runtime must agree on.

    The cache key is derived from this, so a prompt that gained a line break in a source file still
    resolves to the audio rendered for it.
    """

    return " ".join(text.split())


def cache_name(text: str, language: str) -> str:
    """Filename for one rendered prompt. The key IS the filename - no manifest to keep in sync."""

    digest = hashlib.sha1(f"{language}\n{normalize(text)}".encode()).hexdigest()
    return f"{digest}.wav"


class VoiceBank:
    def __init__(
        self,
        piper_binary: Path,
        voice_dir: Path,
        flite_binary: Path,
        flite_voice_dir: Path,
        prerendered_dir: Path | None = None,
    ) -> None:
        self.piper_binary = Path(piper_binary)
        self.voice_dir = Path(voice_dir)
        self.flite_binary = Path(flite_binary)
        self.flite_voice_dir = Path(flite_voice_dir)
        self.prerendered_dir = Path(prerendered_dir) if prerendered_dir is not None else None
        self._engines: dict[str, PiperTTS | FliteTTS] = {}

    def available(self, language: str) -> bool:
        """A language counts as available only if both its voice AND its engine are installed.

        Pre-rendered audio deliberately does not count. A language whose live engine is missing
        would speak every fixed prompt and then fail on the first line nobody rendered, mid
        interview; falling back to a language that works end to end is the lesser harm.
        """

        try:
            spec = profile(language)
        except ValueError:
            return False
        engine = self.piper_binary if spec.engine == "piper" else self.flite_binary
        return engine.exists() and self._voice_path(spec).exists()

    def missing(self, languages: list[str]) -> list[str]:
        return [code for code in languages if not self.available(code)]

    def prerendered(self, text: str, language: str) -> bytes | None:
        """Rendered audio for this exact prompt, or None if it was never rendered."""

        if self.prerendered_dir is None:
            return None
        path = self.prerendered_dir / language / cache_name(text, language)
        try:
            return path.read_bytes()
        except OSError:
            # A missing file is the normal miss. An unreadable one must degrade to live synthesis
            # rather than silence a prompt the patient is waiting on.
            return None

    def synthesize(self, text: str, language: str) -> bytes:
        cached = self.prerendered(text, language)
        if cached is not None:
            return cached

        spec = profile(language)
        engine = self._engines.get(language)
        if engine is None:
            voice = self._voice_path(spec)
            if not voice.exists():
                raise FileNotFoundError(f"No {spec.engine} voice for {language} at {voice}")
            engine = (
                PiperTTS(self.piper_binary, voice)
                if spec.engine == "piper"
                else FliteTTS(self.flite_binary, voice)
            )
            self._engines[language] = engine
        if isinstance(engine, FliteTTS):
            return engine.synthesize(text, duration_stretch=spec.duration_stretch)
        return engine.synthesize(text)

    def _voice_path(self, spec: LanguageProfile) -> Path:
        root = self.voice_dir if spec.engine == "piper" else self.flite_voice_dir
        return root / spec.voice
