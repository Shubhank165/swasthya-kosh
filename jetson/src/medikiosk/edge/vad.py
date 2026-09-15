"""Silero VAD (ONNX) plus the utterance segmenter that turns frame probabilities into turns.

The segmenter is deliberately free of audio-device and model dependencies so it can be tested
without hardware.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

SAMPLE_RATE = 16000
FRAME_SAMPLES = 512  # Silero v5 consumes exactly 512 samples at 16 kHz (32 ms).
FRAME_BYTES = FRAME_SAMPLES * 2
CONTEXT_SAMPLES = 64  # The v5 graph expects the previous 64 samples prepended to every frame.


class SileroVAD:
    """Speech probability per 32 ms frame, on CPU: this model is too small to justify CUDA."""

    def __init__(self, model_path: Path | str) -> None:
        import numpy as np
        import onnxruntime as ort

        self._np = np
        options = ort.SessionOptions()
        options.log_severity_level = 3
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.reset()

    def reset(self) -> None:
        self._state = self._np.zeros((2, 1, 128), dtype=self._np.float32)
        self._context = self._np.zeros(CONTEXT_SAMPLES, dtype=self._np.float32)

    def probability(self, frame: bytes) -> float:
        if len(frame) != FRAME_BYTES:
            raise ValueError(f"Expected {FRAME_BYTES} bytes, got {len(frame)}")
        raw = self._np.frombuffer(frame, dtype=self._np.int16)
        samples = raw.astype(self._np.float32) / 32768.0
        # Without the context the graph still runs but returns a near-zero score for every frame.
        windowed = self._np.concatenate([self._context, samples])
        self._context = samples[-CONTEXT_SAMPLES:]
        output, self._state = self.session.run(
            None,
            {
                "input": windowed.reshape(1, -1),
                "state": self._state,
                "sr": self._np.array(SAMPLE_RATE, dtype=self._np.int64),
            },
        )
        return float(output[0][0])


class SpeechSegmenter:
    """Turns per-frame speech probabilities into complete utterances.

    Keeps a pre-roll so the first syllable of a turn is not clipped, and caps utterance length
    so a noisy room cannot hold the microphone open forever.
    """

    def __init__(
        self,
        threshold: float = 0.5,
        start_ms: int = 160,
        silence_ms: int = 700,
        max_utterance_s: float = 15.0,
        pre_roll_ms: int = 320,
        frame_ms: int = 32,
    ) -> None:
        self.threshold = threshold
        self.frame_ms = frame_ms
        self.start_frames = max(1, start_ms // frame_ms)
        self.silence_frames = max(1, silence_ms // frame_ms)
        self.max_frames = max(1, int(max_utterance_s * 1000) // frame_ms)
        self.pre_roll = deque(maxlen=max(0, pre_roll_ms // frame_ms))
        self.reset()

    def reset(self) -> None:
        self.triggered = False
        self._speech_run = 0
        self._silence_run = 0
        self._frames: list[bytes] = []
        self.pre_roll.clear()

    def feed(self, probability: float, frame: bytes) -> bytes | None:
        """Return the utterance PCM once the turn ends, otherwise None."""

        speech = probability >= self.threshold

        if not self.triggered:
            self.pre_roll.append(frame)
            self._speech_run = self._speech_run + 1 if speech else 0
            if self._speech_run >= self.start_frames:
                self.triggered = True
                self._frames = list(self.pre_roll)
                self._silence_run = 0
                self.pre_roll.clear()
            return None

        self._frames.append(frame)
        self._silence_run = 0 if speech else self._silence_run + 1

        if self._silence_run >= self.silence_frames or len(self._frames) >= self.max_frames:
            utterance = b"".join(self._frames)
            self.reset()
            return utterance
        return None
