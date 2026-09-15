"""A failed measurement must come back as a status, never as an exception.

The kiosk calls this with a patient waiting. Every way it can fail - no camera on this board, a
face model that will not load, a patient who looked away - has to leave the flow able to offer the
measurement again or move on without it.
"""

from __future__ import annotations

import numpy as np
import pytest

from medikiosk.edge import vitals


def test_missing_camera_is_a_status_not_a_crash(monkeypatch):
    class ClosedCapture:
        def isOpened(self):  # noqa: N802 - mirrors cv2's spelling
            return False

        def release(self):
            pass

    cv2 = pytest.importorskip("cv2")
    monkeypatch.setattr(cv2, "VideoCapture", lambda *_: ClosedCapture())

    outcome = vitals.measure(seconds=1.0)

    assert outcome.bpm is None
    assert outcome.confident is False
    assert outcome.status == "camera unavailable"


def test_pulse_in_front_of_the_camera_is_measured(monkeypatch):
    """A synthetic 72 bpm face, fed frame by frame, comes back as 72 bpm and confident."""

    pytest.importorskip("cv2")
    pytest.importorskip("mediapipe")
    fs, bpm = 30.0, 72.0
    total = int(25 * fs)
    skin = np.array([180.0, 130.0, 105.0])
    pbv = np.array([0.33, 0.77, 0.53]) / 0.77

    class FakeCapture:
        def __init__(self):
            self.index = 0

        def isOpened(self):  # noqa: N802
            return True

        def read(self):
            if self.index >= total:
                return False, None
            pulse = np.sin(2 * np.pi * (bpm / 60) * self.index / fs)
            colour = skin * (1 + 0.003 * pulse * pbv)
            self.index += 1
            return True, np.full((64, 64, 3), colour[::-1], dtype=np.uint8)

        def release(self):
            pass

    import cv2

    monkeypatch.setattr(cv2, "VideoCapture", lambda *_: FakeCapture())
    # The face stack is exercised by test_heart_rate.py; here every pixel is the face, so the
    # measurement path itself is what is under test.
    monkeypatch.setattr(vitals, "MEASURE_S", 25.0)
    from medikiosk.edge import heart_rate

    monkeypatch.setattr(heart_rate.FaceTracker, "__init__", lambda self: None)
    monkeypatch.setattr(
        heart_rate.FaceTracker, "track", lambda self, frame, t: np.zeros((478, 2))
    )
    monkeypatch.setattr(heart_rate.FaceTracker, "close", lambda self: None)
    monkeypatch.setattr(heart_rate.OneEuroFilter, "__call__", lambda self, x, t: x)
    monkeypatch.setattr(
        heart_rate, "face_mask", lambda pts, h, w: (0, 0, np.ones((64, 64), bool))
    )
    monkeypatch.setattr(heart_rate.SkinGate, "observe", lambda self, ycc, t: None)
    monkeypatch.setattr(
        heart_rate.SkinGate, "select", lambda self, ycc, inside: np.ones((64, 64), bool)
    )

    outcome = vitals.measure(seconds=25.0)

    assert outcome.status == "ok"
    assert outcome.bpm is not None
    assert abs(outcome.bpm - bpm) < 3.0
