#!/usr/bin/env bash
# Create the echo-cancelled PulseAudio endpoints the offline kiosk loop records from and plays to.
#
# WebRTC AEC only works when the reference signal is the exact stream that reaches the speaker, so
# playback must go to the module's sink (medikiosk_speaker), never straight to the USB card.
#
# The volumes below are calibration, not defaults. At speaker 100% the captured echo clips and AEC
# cannot remove it (the kiosk transcribes its own question); far below 90% patients cannot hear it.
# Re-tune for the final enclosure with scripts/calibrate_audio.sh, which picks the loudest passing
# level, then verify with scripts/test_echo_cancellation.sh.
set -euo pipefail
# shellcheck source=scripts/_audio_common.sh
source "$(dirname "$0")/_audio_common.sh"

MIC_CARD="${MEDIKIOSK_MIC_CARD:-$(detect_mic_card || true)}"
MIC_GAIN="${MEDIKIOSK_MIC_GAIN:-60%}"
# Loudest level that still passes the echo check; scripts/calibrate_audio.sh finds it. Re-run it
# after any hardware or room change: 90% passed in one room and leaked badly in another.
SPEAKER_VOLUME="${MEDIKIOSK_SPEAKER_VOLUME:-80%}"

SOURCE_MASTER="${MEDIKIOSK_SOURCE_MASTER:-$(pactl list short sources | grep -m1 'alsa_input.usb' | cut -f2)}"
SINK_MASTER="${MEDIKIOSK_SINK_MASTER:-$(pactl list short sinks | grep -m1 'alsa_output.usb' | cut -f2)}"

if [[ -z "$SOURCE_MASTER" || -z "$SINK_MASTER" ]]; then
  echo "No USB capture or playback device found. Attach the kiosk microphone and speaker." >&2
  exit 1
fi

echo "microphone : $SOURCE_MASTER"
echo "speaker    : $SINK_MASTER"

for module in $(pactl list short modules | grep module-echo-cancel | cut -f1); do
  pactl unload-module "$module"
done

# aec_args must be quoted as a single value; pactl otherwise splits it and the module fails to load.
pactl load-module module-echo-cancel \
  aec_method=webrtc \
  source_master="$SOURCE_MASTER" \
  sink_master="$SINK_MASTER" \
  source_name=medikiosk_mic \
  sink_name=medikiosk_speaker \
  "aec_args='extended_filter=1 noise_suppression=1 high_pass_filter=1 analog_gain_control=0 digital_gain_control=1'" \
  >/dev/null

set_mic_gain "$MIC_CARD" "$MIC_GAIN"
# Order matters: the AEC sink's volume propagates to its master, so set the master last or the
# calibrated level is silently overwritten.
pactl set-sink-volume medikiosk_speaker 100%
pactl set-sink-volume "$SINK_MASTER" "$SPEAKER_VOLUME"
pactl set-default-source medikiosk_mic
pactl set-default-sink medikiosk_speaker

echo "ready:"
pactl list short sources | grep medikiosk || true
pactl list short sinks | grep medikiosk || true
