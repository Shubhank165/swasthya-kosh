"""Hindi through IndicConformer, everything else through whisper.cpp - chosen by measurement.

33 human Hindi recordings on this Jetson, character error rate after stripping punctuation and
spacing (scripts/indic_asr_server.py has the table):

    whisper large-v3-turbo   mean CER 0.196   p50 0.55 s
    IndicConformer (hi)      mean CER 0.091   p50 0.15 s

Whisper's mean is dragged up by whole-utterance failures - with `language=hi` pinned it still
answered some clips in Latin script or another language. IndicConformer never left Devanagari.
It exists only for Hindi (and Tamil, which the kiosk does not route yet), so English and the
other seven languages stay on whisper, which is also what detects the language of a patient's
first sentence before any language is chosen.

The router falls back to whisper when the Hindi service is down. A kiosk whose Hindi recogniser
died mid-morning should degrade to worse Hindi, not to no Hindi.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from medikiosk.providers.whisper_provider import WhisperCppSTT, WhisperUnavailable


class IndicConformerSTT:
    """Client for scripts/indic_asr_server.py: WAV in, Devanagari text out."""

    def __init__(self, base_url: str = "http://127.0.0.1:11600", timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Health is polled per turn; cache it briefly so a turn costs one request, not two.
        self._healthy_until = 0.0
        self._healthy = False

    def health(self) -> bool:
        now = time.monotonic()
        if now < self._healthy_until:
            return self._healthy
        try:
            with urllib.request.urlopen(f"{self.base_url}/", timeout=2) as response:
                self._healthy = response.status == 200
        except (urllib.error.URLError, OSError, TimeoutError):
            self._healthy = False
        self._healthy_until = now + (30.0 if self._healthy else 5.0)
        return self._healthy

    def transcribe(self, wav_bytes: bytes) -> str:
        request = urllib.request.Request(
            f"{self.base_url}/asr",
            data=wav_bytes,
            headers={"Content-Type": "audio/wav"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as error:
            self._healthy, self._healthy_until = False, time.monotonic() + 5.0
            raise WhisperUnavailable(f"{self.base_url}/asr failed: {error}") from error
        return str(payload.get("text", "")).strip()


class RoutedSTT:
    """One `transcribe(wav, language)` for the kiosk; the model is an implementation detail."""

    def __init__(self, whisper: WhisperCppSTT, indic: IndicConformerSTT | None) -> None:
        self.whisper = whisper
        self.indic = indic

    def health(self) -> bool:
        # Voice is "available" if anything can hear the patient. Whisper is the general case;
        # a Hindi-only kiosk with whisper down but IndicConformer up still has a working mic.
        return self.whisper.health() or bool(self.indic and self.indic.health())

    def transcribe(self, wav_bytes: bytes, language: str | None) -> tuple[str, str | None]:
        if language == "hi" and self.indic is not None and self.indic.health():
            try:
                return self.indic.transcribe(wav_bytes), "hi"
            except WhisperUnavailable:
                pass  # degrade to whisper's Hindi rather than to silence
        return self.whisper.transcribe(wav_bytes, language)
