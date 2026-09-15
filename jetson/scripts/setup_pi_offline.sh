#!/usr/bin/env bash
set -euo pipefail

install_root="${1:-$(pwd)/offline/pi}"
mkdir -p "$install_root"

if ! command -v cmake >/dev/null 2>&1; then
  printf 'cmake is required. Install Raspberry Pi OS packages: cmake build-essential git ffmpeg libasound2-dev\n' >&2
  exit 1
fi

if [[ ! -d "$install_root/whisper.cpp/.git" ]]; then
  git clone --depth 1 https://github.com/ggml-org/whisper.cpp "$install_root/whisper.cpp"
fi

cmake -S "$install_root/whisper.cpp" -B "$install_root/whisper.cpp/build" -DGGML_NATIVE=ON
cmake --build "$install_root/whisper.cpp/build" --config Release -j2
bash "$install_root/whisper.cpp/models/download-ggml-model.sh" base
"$install_root/whisper.cpp/build/bin/quantize" \
  "$install_root/whisper.cpp/models/ggml-base.bin" \
  "$install_root/whisper.cpp/models/ggml-base-q5_0.bin" q5_0

python3 -m venv "$install_root/audio-venv"
"$install_root/audio-venv/bin/python" -m pip install --upgrade pip
"$install_root/audio-venv/bin/python" -m pip install silero-vad deepfilternet

printf 'Whisper.cpp, multilingual base Q5, Silero VAD, and DeepFilterNet are installed.\n'
printf 'Piper voice selection is intentionally separate; choose and validate a licensed hi_IN/en voice.\n'
