#!/usr/bin/env bash
# Keep the multilingual ASR model resident. Loading large-v3-turbo per turn would cost seconds;
# the server pays that once at startup and then answers each turn in inference time alone.
set -euo pipefail

ROOT="${MEDIKIOSK_ROOT:-/home/ubuntu/medikiosk}"
MODEL="${MEDIKIOSK_WHISPER_MODEL:-$ROOT/offline/jetson/models/ggml-large-v3-turbo-q5_0.bin}"
BIN="${MEDIKIOSK_WHISPER_BIN:-$ROOT/offline/jetson/src/whisper.cpp/build/bin/whisper-server}"
PORT="${MEDIKIOSK_WHISPER_PORT:-11500}"
THREADS="${MEDIKIOSK_WHISPER_THREADS:-4}"
# Whisper pads every clip to its full 30 s window. Shrinking the audio context to ~15 s
# halved turn latency with no transcript change; 500 began corrupting words.
AUDIO_CTX="${MEDIKIOSK_WHISPER_AUDIO_CTX:-750}"

if [[ ! -x "$BIN" ]]; then
  echo "whisper-server not built at $BIN" >&2
  exit 1
fi
if [[ ! -f "$MODEL" ]]; then
  echo "model missing at $MODEL" >&2
  exit 1
fi

# Timestamps are dropped because the kiosk never needs word timings, and the default greedy
# decode is kept: a short-utterance kiosk gains little from beam search and cannot afford its
# latency. The language default is auto so each request can carry its own choice.
exec "$BIN" \
  --model "$MODEL" \
  --host 127.0.0.1 \
  --port "$PORT" \
  --threads "$THREADS" \
  --language auto \
  --audio-ctx "$AUDIO_CTX" \
  --no-timestamps
