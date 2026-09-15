#!/usr/bin/env bash
set -euo pipefail

install_root="${1:-$(pwd)/offline/jetson}"
mkdir -p "$install_root"

if command -v ollama >/dev/null 2>&1; then
  ollama pull gemma3:1b
else
  printf 'Ollama is not installed; skipping optional Gemma 3 1B dialogue layer.\n' >&2
fi

python3 -m venv "$install_root/audio-venv"
"$install_root/audio-venv/bin/python" -m pip install --upgrade pip
# Do not install the silero-vad Python package on JetPack: its unconstrained torch dependency can
# pull a generic CUDA runtime that conflicts with NVIDIA's L4T stack. Use the official ONNX model
# with the CPU runtime instead; VAD is small enough that it does not need the GPU.
"$install_root/audio-venv/bin/python" -m pip install 'numpy<2' onnxruntime
mkdir -p "$install_root/models" "$install_root/bin"
curl -fL --retry 3 \
  https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx \
  -o "$install_root/models/silero_vad.onnx"
curl -fL --retry 3 \
  https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-aarch64-unknown-linux-gnu \
  -o "$install_root/bin/deep-filter"
chmod +x "$install_root/bin/deep-filter"
"$install_root/audio-venv/bin/python" scripts/test_offline_audio_runtime.py \
  "$install_root/models/silero_vad.onnx" "$install_root/bin/deep-filter"

if [[ -z "${HF_TOKEN:-}" ]]; then
  printf 'HF_TOKEN is not set. AI4Bharat IndicConformer and IndicF5 are gated/manual installs.\n' >&2
  printf 'Accept their model terms, set HF_TOKEN locally, then follow docs/offline-profiles.md.\n' >&2
fi

printf 'Jetson DeepFilterNet, Silero ONNX, and optional dialogue prerequisites are prepared.\n'
