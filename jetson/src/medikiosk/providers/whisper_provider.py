"""Offline multilingual ASR through a resident whisper.cpp server.

One model serves every supported language, which is the only way nine languages fit on an 8 GB
Jetson: per-language Conformer checkpoints cost ~1.2 GB resident each. The server keeps the model
loaded, so a turn pays inference only, never a reload.

Whisper also reports the language it detected, which is what lets the kiosk switch language from
the patient's first sentence instead of asking them to pick from a list.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid

# Whisper language codes for the languages the kiosk supports end to end.
SUPPORTED = frozenset({"hi", "en", "ta", "te", "bn", "mr", "gu", "kn", "pa"})

# The server reports the language by English name, not by code.
LANGUAGE_NAMES = {
    "hindi": "hi",
    "english": "en",
    "tamil": "ta",
    "telugu": "te",
    "bengali": "bn",
    "marathi": "mr",
    "gujarati": "gu",
    "kannada": "kn",
    "punjabi": "pa",
}


class WhisperUnavailable(RuntimeError):
    """The local whisper.cpp server is not reachable or rejected the request."""


class WhisperCppSTT:
    def __init__(self, base_url: str = "http://127.0.0.1:11500", timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> bool:
        try:
            request = urllib.request.Request(f"{self.base_url}/", method="GET")
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status < 500
        except urllib.error.HTTPError:
            return True  # the server answered, which is all this check needs
        except (urllib.error.URLError, OSError, TimeoutError):
            return False

    def transcribe(self, wav_bytes: bytes, language: str | None = None) -> tuple[str, str | None]:
        """Return (transcript, detected_language). `language=None` lets Whisper detect it."""

        if language is not None and language not in SUPPORTED:
            raise ValueError(f"Unsupported language {language!r}; expected {sorted(SUPPORTED)}")

        fields = {
            "temperature": "0.0",
            "response_format": "verbose_json",
            # Greedy decoding: beam search costs latency the kiosk cannot spare, and a fabricated
            # fluent sentence is worse here than a rough one.
            "language": language or "auto",
        }
        body, content_type = _multipart(fields, "file", "turn.wav", wav_bytes)
        request = urllib.request.Request(
            f"{self.base_url}/inference",
            data=body,
            headers={"Content-Type": content_type},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as error:
            raise WhisperUnavailable(f"{self.base_url}/inference failed: {error}") from error

        text = str(payload.get("text", "")).strip()
        reported = str(payload.get("language", "")).strip().lower()
        detected = LANGUAGE_NAMES.get(reported, reported if reported in SUPPORTED else None)
        return _strip_annotations(text), detected


def _strip_annotations(text: str) -> str:
    """Drop Whisper's bracketed non-speech annotations, e.g. '[BLANK_AUDIO]', '(music)'."""

    cleaned = []
    depth = 0
    for character in text:
        if character in "[(":
            depth += 1
        elif character in "])":
            depth = max(0, depth - 1)
        elif depth == 0:
            cleaned.append(character)
    return " ".join("".join(cleaned).split())


def _multipart(
    fields: dict[str, str],
    file_field: str,
    filename: str,
    content: bytes,
) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n"
            .encode()
        )
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
        f"filename=\"{filename}\"\r\nContent-Type: audio/wav\r\n\r\n".encode()
    )
    parts.append(content)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"
