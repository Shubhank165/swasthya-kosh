"""Hindi speech recognition service: IndicConformer (AI4Bharat, via the Bhashini checkpoints).

Why this exists beside whisper-server
-------------------------------------
Measured on this Jetson against 33 human Hindi recordings (bhashini eval set, labelled by
question id, scored by character error rate after stripping punctuation and spacing):

                        mean CER   exact   p50     p90
    whisper large-v3    0.196      5/33    0.55 s  0.62 s
    IndicConformer      0.091      4/33    0.15 s  0.16 s

Whisper's mean is dragged up by catastrophic failures - with `language=hi` pinned it still
answered some Hindi clips in Latin script or another language entirely ("Kall mósam kisa
raheega?"). IndicConformer never left Devanagari. It has its own failure class - it drops
matras and once heard इंसुलिन as पेंसिलिन - which is what the LLM correction pass downstream
is for. It has no English model, so English stays on whisper.

Run with the Bhashini venv (CUDA onnxruntime + torch). Loads ASR only: the NMT and TTS
engines in that stack would cost ~3 GB for nothing the kiosk uses.

    POST /asr   body: WAV bytes, 16 kHz mono   ->  {"text": "...", "seconds": 0.15}
    GET  /      ->  200 once the model is loaded and warm
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

ROOT = os.environ.get("BHASHINI_ROOT", "/home/ubuntu/bhashini_models")
sys.path.insert(0, ROOT)

from asr.infer import ASRInference  # noqa: E402

MAX_BODY = 8 * 1024 * 1024  # 15 s of 16 kHz mono PCM is ~480 KB; this is generous.

engine = ASRInference(checkpoint_dir=os.path.join(ROOT, "asr", "checkpoints"))
# One inference at a time: the GPU session is not worth contending on, and turns are serial.
lock = Lock()


def silence_wav(seconds: float = 1.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buffer.getvalue()


def transcribe(wav_bytes: bytes) -> str:
    with lock:
        result = engine.infer(base64.b64encode(wav_bytes).decode(), "hi")
    text = result.get("text") if isinstance(result, dict) else result
    return (text or "").strip()


# The first call pays CUDA/TensorRT initialisation (tens of seconds). Pay it here, not on a
# patient's first answer.
transcribe(silence_wav())


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        self._json(200, {"model": "indicconformer-hi", "ready": True})

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        if self.path != "/asr":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_BODY:
            self._json(413, {"error": "audio too large or empty"})
            return
        started = time.monotonic()
        try:
            text = transcribe(self.rfile.read(length))
        except Exception as exc:  # noqa: BLE001 - report the type, never crash the server
            self._json(500, {"error": type(exc).__name__})
            return
        self._json(200, {"text": text, "seconds": round(time.monotonic() - started, 3)})

    def log_message(self, *args) -> None:  # keep patient speech out of the journal
        pass


if __name__ == "__main__":
    port = int(os.environ.get("INDIC_ASR_PORT", "11600"))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
