#!/usr/bin/env bash
set -u

profile="${1:-jetson}"
failures=0
warnings=0

pass() { printf '[PASS] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; warnings=$((warnings + 1)); }
fail() { printf '[FAIL] %s\n' "$1"; failures=$((failures + 1)); }

printf 'MediKiosk readiness profile: %s\n' "$profile"

command -v python3 >/dev/null 2>&1 && pass 'Python is available' || fail 'Python is missing'
command -v ffmpeg >/dev/null 2>&1 && pass 'FFmpeg is available' || warn 'FFmpeg is missing'
command -v arecord >/dev/null 2>&1 && pass 'ALSA capture tools are available' || fail 'arecord is missing'
command -v aplay >/dev/null 2>&1 && pass 'ALSA playback tools are available' || fail 'aplay is missing'

capture_devices="$(arecord -l 2>/dev/null || true)"
playback_devices="$(aplay -l 2>/dev/null || true)"

if [[ "$profile" == "jetson" ]] && \
  ! printf '%s\n' "$capture_devices" | grep '^card ' | grep -qv 'NVIDIA Jetson Orin Nano APE'; then
  fail 'Only Jetson APE virtual capture endpoints are visible; attach the intended microphone'
elif printf '%s\n' "$capture_devices" | grep -q '^card '; then
  pass 'An audio capture device is attached'
else
  fail 'No audio capture device is visible; attach the intended USB/directional microphone'
fi

if printf '%s\n' "$playback_devices" | grep -q '^card '; then
  pass 'An audio playback device is attached'
else
  warn 'No ALSA playback device is visible; verify the intended speaker/output'
fi

if command -v tailscale >/dev/null 2>&1 && tailscale status >/dev/null 2>&1; then
  pass 'Tailscale is connected'
else
  warn 'Tailscale is unavailable or disconnected'
fi

if [[ "$profile" == "jetson" ]]; then
  command -v ollama >/dev/null 2>&1 && pass 'Ollama is available' || warn 'Ollama is missing (Gemma dialogue is optional)'
  if command -v ollama >/dev/null 2>&1 && ollama list 2>/dev/null | grep -q '^gemma3:1b'; then
    pass 'Gemma 3 1B is installed'
  else
    warn 'Gemma 3 1B is not installed'
  fi
  [[ -n "${HF_TOKEN:-}" ]] && pass 'HF_TOKEN is set for gated AI4Bharat models' || warn 'HF_TOKEN is not set'
fi

printf 'Summary: %d failure(s), %d warning(s)\n' "$failures" "$warnings"
exit "$failures"
