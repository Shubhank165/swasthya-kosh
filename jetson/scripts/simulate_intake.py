#!/usr/bin/env python3
"""Drive a full offline intake with a scripted patient, through a virtual microphone.

This exercises VAD, segmentation, local ASR, the state machine, the red-flag rules, and local TTS
without a person in the room. It does NOT test acoustics: a null sink has no echo, no room noise,
and no distance, so echo cancellation and real barge-in still need
`scripts/test_echo_cancellation.sh` plus a human in the final enclosure.

    python3 scripts/simulate_intake.py "सीने में दर्द" "दो दिन से" "सात" "हाँ"
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from medikiosk.config import Settings  # noqa: E402
from medikiosk.providers.voices import VoiceBank  # noqa: E402

SINK = "sim_patient"
LANGUAGE = os.environ.get("MEDIKIOSK_LANG", "hi")

_settings = Settings()
_voices = VoiceBank(
    REPO / _settings.piper_binary,
    REPO / _settings.voice_dir,
    _settings.flite_binary,
    _settings.flite_voice_dir,
)


def synthesize(text: str, path: Path) -> None:
    """The scripted patient speaks with the same offline voices the kiosk uses."""

    path.write_bytes(_voices.synthesize(text, LANGUAGE))


def main(lines: list[str]) -> int:
    if not lines:
        print(__doc__)
        return 2

    module = subprocess.run(
        ["pactl", "load-module", "module-null-sink", f"sink_name={SINK}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    workdir = Path(tempfile.mkdtemp())
    clips = []
    for index, line in enumerate(lines):
        clip = workdir / f"turn{index}.wav"
        synthesize(line, clip)
        clips.append(clip)

    environment = {
        **os.environ,
        "PYTHONPATH": str(REPO / "src"),
        "MIC_SOURCE": f"{SINK}.monitor",
        "SILERO_MODEL_PATH": str(REPO / "offline/jetson/models/silero_vad.onnx"),
    }
    runtime = subprocess.Popen(
        [sys.executable, "-m", "medikiosk.edge.runtime"],
        cwd=REPO,
        env=environment,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )

    remaining = iter(clips)
    barge_in = os.environ.get("MEDIKIOSK_SIMULATE_BARGE_IN") == "1"

    def play_next(delay: float = 0.0) -> None:
        clip = next(remaining, None)
        if clip is None:
            return
        if delay:
            time.sleep(delay)
        subprocess.run(["paplay", f"--device={SINK}", str(clip)], check=False)

    def feed() -> None:
        assert runtime.stderr is not None
        for raw in runtime.stderr:
            sys.stderr.write(raw)
            sys.stderr.flush()
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            name = event.get("event")
            if barge_in and name == "speaking" and "?" in str(event.get("text", "")):
                # Answer over the top of the question to prove playback stops on speech.
                play_next(delay=0.8)
            elif name == "listening":
                play_next()

    reader = threading.Thread(target=feed, daemon=True)
    reader.start()

    # communicate() would race the feeder thread for the same stderr pipe and swallow the cues.
    try:
        assert runtime.stdout is not None
        report = runtime.stdout.read()
        runtime.wait(timeout=300)
    except subprocess.TimeoutExpired:
        runtime.kill()
        report = ""
    finally:
        reader.join(timeout=5)
        subprocess.run(["pactl", "unload-module", module], check=False)

    print(report)
    return runtime.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
