"""One bounded heart-rate measurement from the kiosk camera, with no window on screen.

edge/heart_rate.py owns the signal work - face tracking, the skin mask, POS/CHROM and the
spectral estimate - but it is built around a live session: camera and processor threads, a CSV
log per run, and either an OpenCV window or an MJPEG server. A patient at the kiosk needs none of
that. They look at the camera for twenty seconds and get one number, and the camera closes again.

So this reuses that module's maths and supplies its own short capture loop. Nothing here is a
diagnosis: an unconfident estimate is reported as unconfident rather than rounded into a vital
sign, and staff review every record anyway.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np

# Long enough for the estimator, which needs MIN_WINDOW_S (8 s) of clean signal and rejects
# stretches where the face was lost, and short enough that a patient will sit still for it.
MEASURE_S = 20.0

# One camera, one owner. A measurement holds this for its whole run; the preview takes it only
# when nobody is measuring, and otherwise shows the frame the measurement last stored.
_camera = threading.Lock()
_latest_lock = threading.Lock()
_latest_jpeg: bytes | None = None
_latest_face = False


def _remember(frame, face_found: bool) -> None:
    """Keep the most recent frame as a JPEG, cheaply enough to do it every frame."""

    global _latest_jpeg, _latest_face
    try:
        import cv2

        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
    except Exception:  # noqa: BLE001 - a preview is never worth failing a measurement for
        return
    if not ok:
        return
    with _latest_lock:
        _latest_jpeg = buffer.tobytes()
        _latest_face = face_found


def preview_jpeg(camera: int | str = 0) -> tuple[bytes | None, bool]:
    """The current camera view as a JPEG, and whether a face was found in it.

    During a measurement this is whatever the capture loop last saw, which is the honest answer:
    the camera is busy and that frame is seconds old at most. Otherwise the camera is opened for
    one frame and released again, so aiming it does not require starting a measurement.
    """

    if _camera.acquire(blocking=False):
        try:
            import cv2

            capture = cv2.VideoCapture(camera)
            try:
                if capture.isOpened():
                    for _ in range(3):  # the first frames off a USB camera are often black
                        ok, frame = capture.read()
                    if ok:
                        _remember(frame, False)
            finally:
                capture.release()
        except Exception:  # noqa: BLE001 - fall through to whatever was last stored
            pass
        finally:
            _camera.release()
    with _latest_lock:
        return _latest_jpeg, _latest_face


@dataclass(frozen=True)
class Vitals:
    """The outcome of one attempt. `bpm` is None unless there was a usable estimate."""

    bpm: float | None
    confident: bool
    status: str


def measure(camera: int | str = 0, seconds: float = MEASURE_S) -> Vitals:
    """Watch the camera for `seconds` and return a heart rate, or why there isn't one.

    Every failure is a status string, never an exception: a missing camera, a patient who looked
    away, or a face the tracker could not hold must leave the kiosk on the same screen, able to
    offer the measurement again or move on without it.
    """

    try:
        import cv2

        from medikiosk.edge.heart_rate import (
            MIN_SKIN_PX,
            FaceTracker,
            OneEuroFilter,
            SkinGate,
            analyze_window,
            face_mask,
        )
    except Exception as error:  # noqa: BLE001 - any import failure is "not available here"
        return Vitals(None, False, f"heart rate unavailable: {error}")

    if not _camera.acquire(timeout=5.0):
        return Vitals(None, False, "camera busy")
    capture = cv2.VideoCapture(camera)
    if not capture.isOpened():
        capture.release()
        _camera.release()
        return Vitals(None, False, "camera unavailable")

    try:
        tracker = FaceTracker()
    except Exception as error:  # noqa: BLE001 - missing face model, no GPU, etc.
        capture.release()
        _camera.release()
        return Vitals(None, False, f"face tracking unavailable: {error}")

    gate, smoother = SkinGate(), OneEuroFilter()
    samples: list[tuple[float, float, float, float, float]] = []
    start = time.monotonic()
    frames = 0
    try:
        while time.monotonic() - start < seconds:
            ok, frame = capture.read()
            if not ok:
                break
            now = time.monotonic() - start
            height, width = frame.shape[:2]
            points = tracker.track(frame, now)
            rgb: tuple[float, float, float] = (np.nan, np.nan, np.nan)
            valid = False
            if points is None:
                smoother.reset()
            else:
                points = smoother(points, now)
                geometry = face_mask(points, height, width)
                if geometry is not None:
                    top, left, inside = geometry
                    crop = frame[top:top + inside.shape[0], left:left + inside.shape[1]]
                    ycc = cv2.cvtColor(crop, cv2.COLOR_BGR2YCrCb)
                    # The skin gate learns this patient's colour; it only needs occasional looks.
                    if frames % 10 == 0:
                        gate.observe(ycc[inside], now)
                    selected = gate.select(ycc, inside)
                    if int(selected.sum()) >= MIN_SKIN_PX:
                        rgb = tuple(crop[selected].mean(axis=0)[::-1])
                        valid = True
            samples.append((now, *rgb, float(valid)))
            # Publish as we go: this is what makes the camera aimable from the tablet.
            _remember(frame, valid)
            frames += 1
    except Exception as error:  # noqa: BLE001 - a capture fault is a failed measurement, not a crash
        return Vitals(None, False, f"measurement failed: {error}")
    finally:
        capture.release()
        tracker.close()
        _camera.release()

    if len(samples) < 2:
        return Vitals(None, False, "no frames from camera")
    data = np.asarray(samples, dtype=np.float64)
    result, status = analyze_window(data[:, 0], data[:, 1:4], data[:, 4] > 0, seconds)
    if result is None:
        seen = float(data[:, 4].mean()) if len(data) else 0.0
        if seen < 0.5:
            return Vitals(None, False, "no face in view - point the camera at the patient's face")
        return Vitals(None, False, status)
    return Vitals(round(float(result.bpm), 1), bool(result.confident), "ok")
