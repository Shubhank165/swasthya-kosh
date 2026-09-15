#!/usr/bin/env bash
# Thin wrapper so calibrate_audio.sh and older notes keep working. The check itself is Python
# because it must use the same voices and ASR as the intake loop.
set -euo pipefail
ROOT="${MEDIKIOSK_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
PYTHON="${MEDIKIOSK_PYTHON:-$ROOT/offline/jetson/audio-venv/bin/python}"
exec "$PYTHON" "$ROOT/scripts/test_echo_cancellation.py" "$@"
