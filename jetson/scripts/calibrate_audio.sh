#!/usr/bin/env bash
# Find the LOUDEST speaker setting the room still passes echo cancellation at.
#
# Too quiet is a real failure: patients cannot hear the question, and a mic turned up to compensate
# clips. This sweeps the speaker from loud to quiet and stops at the first level that passes
# scripts/test_echo_cancellation.sh, then leaves the device set there.
set -eu
# shellcheck source=scripts/_audio_common.sh
source "$(dirname "$0")/_audio_common.sh"

SINK="${MEDIKIOSK_SINK_MASTER:-$(pactl list short sinks | grep -m1 'alsa_output.usb' | cut -f2)}"
MIC_CARD="${MEDIKIOSK_MIC_CARD:-$(detect_mic_card || true)}"
MIC_GAIN="${MEDIKIOSK_MIC_GAIN:-60%}"
LEVELS="${MEDIKIOSK_SPEAKER_LEVELS:-100% 90% 80% 70% 60% 50% 40%}"

if [[ -z "$SINK" ]]; then
  echo "No USB playback device found." >&2
  exit 1
fi

# The virtual AEC sink must stay at unity or its own attenuation hides the real speaker level.
# It propagates to the master, so it is set before every master change, never after.
pactl set-sink-volume medikiosk_speaker 100% 2>/dev/null || true
set_mic_gain "$MIC_CARD" "$MIC_GAIN"

for level in $LEVELS; do
  pactl set-sink-volume "$SINK" "$level"
  printf '\n=== speaker %s ===\n' "$level"
  if bash "$(dirname "$0")/test_echo_cancellation.sh"; then
    echo
    echo "USE THIS: speaker $level, mic $MIC_GAIN (loudest level that still passes)"
    echo "Persist it by setting MEDIKIOSK_SPEAKER_VOLUME=$level and MEDIKIOSK_MIC_GAIN=$MIC_GAIN"
    echo "in the environment that runs scripts/setup_jetson_audio.sh."
    exit 0
  fi
done

echo
echo "No level passed. The microphone is hearing too much of the speaker:"
echo "  - move the microphone away from the speaker, or point them apart"
echo "  - lower MEDIKIOSK_MIC_GAIN and re-run"
exit 1
