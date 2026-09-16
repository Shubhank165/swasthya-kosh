"""Every voice must leave the kiosk at the same loudness, with headroom.

Piper renders hot enough to clip and Flite's Indic voices come out four times quieter, which on a
kiosk speaker is a shout followed by a mumble. The gain stage that fixes it must not introduce the
defect it removes, so the ceiling is checked on the loud case as well as the quiet one.
"""

from __future__ import annotations

import array
import io
import math
import wave

from medikiosk.providers.voices import PEAK_CEILING, TARGET_RMS, level


def tone(amplitude: float, seconds: float = 0.5, rate: int = 22050) -> bytes:
    samples = array.array(
        "h",
        (
            int(amplitude * 32767 * math.sin(2 * math.pi * 220 * n / rate))
            for n in range(int(rate * seconds))
        ),
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


def measured(wav_bytes: bytes) -> tuple[float, float, int]:
    with wave.open(io.BytesIO(wav_bytes)) as handle:
        rate = handle.getframerate()
        samples = array.array("h")
        samples.frombytes(handle.readframes(handle.getnframes()))
    peak = max(abs(s) for s in samples) / 32768
    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5 / 32768
    return peak, rms, rate


def test_quiet_voice_is_lifted():
    peak, rms, rate = measured(level(tone(0.08)))

    assert rms > 0.08
    assert peak <= PEAK_CEILING + 0.01
    assert rate == 22050


def test_hot_voice_is_pulled_below_the_ceiling():
    peak, _, _ = measured(level(tone(1.0)))

    assert peak <= PEAK_CEILING + 0.01


def test_loud_and_quiet_end_up_at_the_same_level():
    _, quiet_rms, _ = measured(level(tone(0.08)))
    _, loud_rms, _ = measured(level(tone(1.0)))

    # Both are pure tones, so whichever bound binds, they must land together.
    assert abs(quiet_rms - loud_rms) < 0.02
    assert min(quiet_rms, loud_rms) > TARGET_RMS / 2


def test_silence_is_left_alone():
    silence = tone(0.0)

    assert level(silence) == silence
