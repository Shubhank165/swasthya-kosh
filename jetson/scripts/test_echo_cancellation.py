#!/usr/bin/env python3
"""Hardware acceptance check: the kiosk must not transcribe its own spoken question.

Plays a prompt through the echo-cancelled sink while recording the echo-cancelled source, then
asks the local ASR what it heard. Anything intelligible coming back means the microphone is
hearing the speaker, and every prompt will be answered by the kiosk itself.

Uses the same voices and the same ASR as the intake loop, so a pass here is a statement about the
stack that actually ships - not about a service that happens to be running.

    python3 scripts/test_echo_cancellation.py [--language hi] [--repeats 2]
"""

from __future__ import annotations

import argparse
import audioop
import subprocess
import sys
import time
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from medikiosk.clinical.translations import QUESTION_TEXT  # noqa: E402
from medikiosk.config import Settings  # noqa: E402
from medikiosk.edge.runtime import pcm_to_wav  # noqa: E402
from medikiosk.providers.voices import VoiceBank  # noqa: E402
from medikiosk.providers.whisper_provider import WhisperCppSTT  # noqa: E402

# Echo is what rises *above* the room, not an absolute level. An OPD is never silent, and a fixed
# threshold fails a quiet-but-noisy room while passing a loud one.
ECHO_MARGIN = 2.0  # captured RMS may not exceed ambient by more than this factor
ABSOLUTE_FLOOR_RMS = 400  # below this, any ratio is noise on noise
NOISY_ROOM_RMS = 1500  # above this the room itself will drive the VAD


def record(source: str, seconds: float | None, path: Path, during=None) -> bytes:
    """Capture from the echo-cancelled source, optionally running `during` while recording."""

    path.parent.mkdir(exist_ok=True)
    recorder = subprocess.Popen(
        [
            "parecord",
            f"--device={source}",
            "--format=s16le",
            "--rate=16000",
            "--channels=1",
            "--file-format=wav",
            str(path),
        ],
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.5)
        if during is not None:
            during()
        if seconds is not None:
            time.sleep(seconds)
        time.sleep(0.5)
    finally:
        recorder.terminate()
        recorder.wait(timeout=5)
    with wave.open(str(path)) as handle:
        return handle.readframes(handle.getnframes())


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="hi")
    parser.add_argument("--repeats", type=int, default=2, help="prompts played back to back")
    parser.add_argument("--text", default=None, help="override the spoken prompt")
    args = parser.parse_args(argv)

    settings = Settings()
    voices = VoiceBank(
        REPO / settings.piper_binary,
        REPO / settings.voice_dir,
        settings.flite_binary,
        settings.flite_voice_dir,
    )
    whisper = WhisperCppSTT(settings.whisper_url)
    if not whisper.health():
        print(f"whisper.cpp server not reachable at {settings.whisper_url}")
        return 2

    ambient = record(settings.mic_source, seconds=2.0, path=REPO / "data" / "echo_ambient.wav")
    if not ambient or audioop.rms(ambient, 2) == 0:
        # Silence is not a pass. An empty capture means the source is missing or still settling,
        # and scoring it would certify a kiosk that cannot hear at all.
        print(
            f"SETUP ERROR: captured no audio from '{settings.mic_source}' "
            f"({len(ambient)} bytes). Run scripts/setup_jetson_audio.sh in this same shell "
            "session - the PulseAudio endpoints do not survive a session ending."
        )
        return 2
    ambient_rms = audioop.rms(ambient, 2)
    print(f"ambient   : rms={ambient_rms} peak={audioop.max(ambient, 2)}")
    if ambient_rms > NOISY_ROOM_RMS:
        print(
            f"WARNING: the room is loud (ambient rms {ambient_rms} > {NOISY_ROOM_RMS}). "
            "Echo cancellation can still pass here, but the VAD will trigger on room noise and "
            "short answers will be lost. Re-test somewhere quieter or move the microphone closer."
        )

    text = args.text or QUESTION_TEXT["ask_complaint"][args.language]
    prompt = REPO / "data" / "echo_prompt.wav"
    prompt.parent.mkdir(exist_ok=True)
    prompt.write_bytes(voices.synthesize(text, args.language))

    def play() -> None:
        for _ in range(args.repeats):
            subprocess.run(
                ["paplay", f"--device={settings.speaker_sink}", str(prompt)],
                check=False,
            )

    pcm = record(settings.mic_source, seconds=None, path=REPO / "data" / "echo_captured.wav",
                 during=play)
    rms, peak = audioop.rms(pcm, 2), audioop.max(pcm, 2)
    heard, _ = whisper.transcribe(pcm_to_wav(pcm), args.language)

    print(f"spoken    : {text}")
    print(f"captured  : rms={rms} peak={peak}")
    ratio = rms / max(ambient_rms, 1)
    print(f"echo rise : {ratio:.2f}x over ambient (limit {ECHO_MARGIN}x)")
    print(f"heard back: {heard!r}")

    # Whisper emits stray fragments from near-silence, which is not leakage. What matters is
    # whether a real word of the prompt came back, or the speaker measurably raised the noise
    # floor the VAD sees.
    # Short function words (के, में, है) turn up in any hallucinated Hindi, so matching them
    # proves nothing. Leakage means a distinctive word of the prompt came back.
    leaked = sorted({word for word in text.split() if len(word) >= 4 and word in heard})
    # Two ways to be acceptable: the residual is too quiet for the VAD to call it speech at all,
    # or it barely rises above the room. A loud room makes the ratio meaningless, which is why the
    # absolute floor is checked first.
    quiet_enough = rms <= ABSOLUTE_FLOOR_RMS
    loud = not quiet_enough and ratio > ECHO_MARGIN
    if leaked or loud:
        print(f"FAIL: leaked_words={leaked} echo_rise={ratio:.2f}x residual_rms={rms}")
        print("Lower the speaker volume or the mic gain, or run scripts/calibrate_audio.sh.")
        return 1
    if ambient_rms > NOISY_ROOM_RMS:
        # Loud room noise swamps the echo and makes the ratio meaningless: it would certify any
        # speaker level, including one that fails the moment the room goes quiet.
        print(
            "INCONCLUSIVE: room too loud to measure echo. This is not a pass - re-run somewhere "
            f"quieter (ambient rms {ambient_rms}, need under {NOISY_ROOM_RMS})."
        )
        return 2
    reason = (
        f"residual rms {rms} is below the {ABSOLUTE_FLOOR_RMS} the VAD needs to call it speech"
        if quiet_enough
        else f"echo rise {ratio:.2f}x is within the {ECHO_MARGIN}x limit"
    )
    print(f"PASS: the kiosk does not hear itself ({reason}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
