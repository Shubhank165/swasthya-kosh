#!/usr/bin/env bash
# Shared audio helpers. Sourced, not executed.

# ALSA card numbers are assigned in probe order and move between boots. Find the capture card that
# actually owns a 'Mic' control rather than trusting an index that was right once.
detect_mic_card() {
  local card
  for card in $(arecord -l | grep -oE '^card [0-9]+' | grep -oE '[0-9]+' | sort -u); do
    if amixer -c "$card" scontrols 2>/dev/null | grep -q "'Mic'"; then
      echo "$card"
      return 0
    fi
  done
  return 1
}

set_mic_gain() {
  local card="$1" gain="$2"
  if [[ -n "$card" ]]; then
    amixer -c "$card" sset Mic "$gain" >/dev/null
    echo "mic gain   : card $card at $gain"
  else
    echo "WARNING: no capture card exposes a 'Mic' control; gain left untouched" >&2
  fi
}
