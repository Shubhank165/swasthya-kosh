"""Live camera heart rate (rPPG), end to end, for the Jetson edge kiosk.

Every frame:
  Camera (DirectShow on Windows, V4L2 on Linux/Jetson, auto/manual exposure)
  -> MediaPipe face landmarks, smoothed with a One Euro filter
  -> full-face skin mask: face oval minus eyes/brows/mouth, skin-colour gate learned from the face
  -> mean R, G, B of the skin pixels, with the frame timestamp

Every second, on the last --window seconds:
  cut brightness jumps and face gaps -> resample onto a uniform 30 Hz grid
  -> smoothness-priors detrend (Tarvainen 2002) -> POS and CHROM pulse extraction
  -> 0.7-4 Hz band-pass -> spectral peak = heart rate, SNR + POS/CHROM agreement = confidence

Runs either:
  1. Desktop OpenCV window (interactive GUI with buttons, charts, hotkeys)
  2. Web server over the private Tailnet / local HTTP (--web or auto-fallback if headless/no DISPLAY)
     - Live visual canvas: http://<tailnet-ip>:8092/
     - MJPEG stream: /stream.mjpg
     - Snapshot: /frame.jpg
     - Real-time JSON vitals: /api/vitals

Usage:
    python -m medikiosk.edge.heart_rate --selftest   # check signal maths on synthetic data
    python -m medikiosk.edge.heart_rate              # run live (GUI or web over Tailscale)
    python -m medikiosk.edge.heart_rate --web        # force web server mode over Tailnet

Methods:
  POS      Wang, den Brinker, Stuijk & de Haan (2017), IEEE TBME 64(7):1479-1491
  CHROM    de Haan & Jeanne (2013), IEEE TBME 60(10):2878-2886
  Detrend  Tarvainen, Ranta-aho & Karjalainen (2002), IEEE TBME 49(2):172-175
  Landmark smoothing  Casiez, Roussel & Vogel (2012), 1 euro filter, CHI
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import io
import json
import os
import platform
import queue
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
from scipy import signal, sparse
from scipy.ndimage import uniform_filter1d
from scipy.sparse.linalg import splu

# Model discovery: check project-local models or offline Jetson models
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent
MODEL_SEARCH_PATHS = [
    REPO_ROOT / "models" / "face_landmarker.task",
    REPO_ROOT / "offline" / "jetson" / "models" / "face_landmarker.task",
    HERE / "models" / "face_landmarker.task",
]
DEFAULT_MODEL_PATH = REPO_ROOT / "models" / "face_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)

# ----------------------------------------------------------------------------- tuning
FS = 30.0                  # analysis grid, Hz
HR_BAND = (0.7, 4.0)       # 42-240 bpm
MIN_WINDOW_S = 8.0         # shortest clean stretch that gets an estimate
JUMP_FRAC = 0.15           # skin brightness this far from the window median = light/exposure jump
SNR_MIN_DB = 0.0           # below this the spectral peak is not trusted
AGREE_BPM = 3.0            # POS and CHROM must agree this closely to call it confident
MIN_FACE_G = 40            # mean skin green below this: too dark to hold a pulse
MIN_SKIN_PX = 300

# MediaPipe face mesh indices
FACE_OVAL = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377,
    152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109,
]
FACE_EXCLUDE = [
    [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246,
     70, 63, 105, 66, 107, 55, 65, 52, 53, 46],                                        # right eye + brow
    [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466,
     300, 293, 334, 296, 336, 285, 295, 282, 283, 276],                                # left eye + brow
    [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185],  # mouth
]
EXCLUDE_GROW = 1.15
EYE_OUTER = (33, 263)

def _bgr(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)

PAGE, SURFACE = _bgr("#0d0d0d"), _bgr("#1a1a19")
INK, INK2, MUTED = _bgr("#ffffff"), _bgr("#c3c2b7"), _bgr("#898781")
GRID, AXIS = _bgr("#2c2c2a"), _bgr("#383835")
SERIES = _bgr("#3987e5")
GOOD, WARN, BAD = _bgr("#0ca30c"), _bgr("#fab219"), _bgr("#d03b3b")
FONT = cv2.FONT_HERSHEY_SIMPLEX
WINDOW_NAME = "Heart rate (camera)"
CANVAS_H = 800
PRESETS_S = (30, 60, 120, 180)

# ----------------------------------------------------------------------------- signal
_SOS = signal.butter(4, HR_BAND, btype="bandpass", fs=FS, output="sos")
_DETREND: dict[int, object] = {}
_DETREND_LOCK = threading.Lock()

def bandpass(x: np.ndarray) -> np.ndarray:
    return signal.sosfiltfilt(_SOS, x)

def detrend_ratio(x: np.ndarray, cutoff_hz: float = 0.3) -> np.ndarray:
    n = len(x)
    with _DETREND_LOCK:
        lu = _DETREND.get(n)
        if lu is None:
            lam = (FS / (2 * np.pi * cutoff_hz)) ** 2
            d2 = sparse.diags([1.0, -2.0, 1.0], [0, 1, 2], shape=(n - 2, n))
            lu = splu((sparse.identity(n) + lam ** 2 * (d2.T @ d2)).tocsc())
            if len(_DETREND) > 16:
                _DETREND.clear()
            _DETREND[n] = lu
        trend = np.column_stack([lu.solve(x[:, c]) for c in range(x.shape[1])])
    return x / trend

def pos(rgb: np.ndarray, fs: float = FS, win_s: float = 1.6) -> np.ndarray:
    n = len(rgb)
    l = int(np.ceil(win_s * fs))
    if n < l:
        return np.zeros(n)
    win = np.moveaxis(np.lib.stride_tricks.sliding_window_view(rgb, l, axis=0), 1, 2)
    cn = win / win.mean(axis=1, keepdims=True)
    s1 = cn[..., 1] - cn[..., 2]
    s2 = -2.0 * cn[..., 0] + cn[..., 1] + cn[..., 2]
    sd2 = s2.std(axis=1, keepdims=True)
    alpha = np.divide(s1.std(axis=1, keepdims=True), sd2, out=np.zeros_like(sd2), where=sd2 > 0)
    p = s1 + alpha * s2
    p -= p.mean(axis=1, keepdims=True)
    h = np.zeros(n)
    for k in range(l):
        h[k:k + len(p)] += p[:, k]
    return h

def chrom(rgb: np.ndarray, fs: float = FS, win_s: float = 1.6) -> np.ndarray:
    n = len(rgb)
    l = int(np.ceil(win_s * fs))
    l += l % 2
    if n < 2 * l:
        return np.zeros(n)
    cn = rgb / uniform_filter1d(rgb, l, axis=0, mode="nearest")
    xf = bandpass(3.0 * cn[:, 0] - 2.0 * cn[:, 1])
    yf = bandpass(1.5 * cn[:, 0] + cn[:, 1] - 1.5 * cn[:, 2])
    hann = signal.windows.hann(l, sym=False)
    out = np.zeros(n)
    for start in range(0, n - l + 1, l // 2):
        seg = slice(start, start + l)
        sy = yf[seg].std()
        s = xf[seg] - (xf[seg].std() / sy if sy > 0 else 0.0) * yf[seg]
        out[seg] += hann * (s - s.mean())
    return out

def estimate_hr(x: np.ndarray, fs: float = FS) -> tuple[float, float, np.ndarray, np.ndarray]:
    n = len(x)
    nfft = max(4096, 1 << int(np.ceil(np.log2(n))))
    f, p = signal.periodogram(x, fs=fs, window="hann", nfft=nfft, detrend="linear")
    band = (f >= HR_BAND[0]) & (f <= HR_BAND[1])
    f0 = float(f[band][np.argmax(p[band])])
    half = max(0.1, 2.0 * fs / n)
    sig = (np.abs(f - f0) <= half) | (np.abs(f - 2 * f0) <= 2 * half)
    noise = float(p[band & ~sig].sum())
    snr = 10 * np.log10(float(p[band & sig].sum()) / noise) if noise > 0 else float("inf")
    return 60.0 * f0, float(snr), f, p

@dataclass
class Result:
    bpm: float
    snr_db: float
    chrom_bpm: float
    confident: bool
    window_s: float
    tu: np.ndarray
    pulse: np.ndarray
    f: np.ndarray
    psd: np.ndarray

def analyze_window(t: np.ndarray, rgb: np.ndarray, valid: np.ndarray, win_s: float) -> tuple[Result | None, str]:
    keep = t >= t[-1] - win_s
    t, rgb, valid = t[keep], rgb[keep], valid[keep]
    if t[-1] - t[0] < MIN_WINDOW_S:
        return None, f"measuring {t[-1] - t[0]:.0f}/{MIN_WINDOW_S:.0f} s"
    if valid.mean() < 0.8:
        return None, "face not found"
    med = np.median(rgb[valid, 1])
    jump = valid & (np.abs(rgb[:, 1] / med - 1) > JUMP_FRAC)
    if jump.any():
        keep = t >= t[np.flatnonzero(jump)[-1]] + 1.0
        t, rgb, valid = t[keep], rgb[keep], valid[keep]
        if len(t) < 2 or t[-1] - t[0] < MIN_WINDOW_S or valid.sum() < 2:
            return None, "light changed, settling"
    tv = t[valid]
    filled = np.column_stack([np.interp(t, tv, rgb[valid, c]) for c in range(3)])
    tu = np.arange(t[0], t[-1], 1.0 / FS)
    x = np.column_stack([np.interp(tu, t, filled[:, c]) for c in range(3)])
    d = detrend_ratio(x)
    p_pos = bandpass(pos(d))
    bpm, snr, f, psd = estimate_hr(p_pos)
    chrom_bpm, _, _, _ = estimate_hr(bandpass(chrom(d)))
    confident = snr >= SNR_MIN_DB and abs(bpm - chrom_bpm) <= AGREE_BPM
    return Result(bpm, snr, chrom_bpm, confident, float(tu[-1] - tu[0]), tu, p_pos, f, psd), "ok"

# ----------------------------------------------------------------------------- face + skin
def ensure_model() -> Path:
    for candidate in MODEL_SEARCH_PATHS:
        if candidate.exists():
            return candidate
    DEFAULT_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading face model to {DEFAULT_MODEL_PATH} ...", flush=True)
    urllib.request.urlretrieve(MODEL_URL, DEFAULT_MODEL_PATH)
    return DEFAULT_MODEL_PATH

class OneEuroFilter:
    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.05, d_cutoff: float = 1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.reset()

    def reset(self) -> None:
        self._x = self._dx = self._t = None

    @staticmethod
    def _alpha(dt: float, cutoff):
        return 1.0 / (1.0 + 1.0 / (2 * np.pi * cutoff * dt))

    def __call__(self, x: np.ndarray, t: float) -> np.ndarray:
        if self._x is None:
            self._x, self._dx, self._t = x.copy(), np.zeros_like(x), t
            return x
        dt = max(t - self._t, 1e-6)
        a_d = self._alpha(dt, self.d_cutoff)
        self._dx = a_d * (x - self._x) / dt + (1 - a_d) * self._dx
        a = self._alpha(dt, self.min_cutoff + self.beta * np.linalg.norm(self._dx, axis=-1, keepdims=True))
        self._x = a * x + (1 - a) * self._x
        self._t = t
        return self._x.copy()

class FaceTracker:
    def __init__(self):
        try:
            import mediapipe as mp
        except ImportError as e:
            raise SystemExit("mediapipe missing: pip install --no-deps mediapipe absl-py flatbuffers") from e
        vision = mp.tasks.vision
        self._mp = mp
        self._lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(ensure_model())),
            running_mode=vision.RunningMode.VIDEO, num_faces=1))
        self._last_ms = -1

    def track(self, bgr: np.ndarray, t: float) -> np.ndarray | None:
        h, w = bgr.shape[:2]
        ms = max(int(t * 1000), self._last_ms + 1)
        self._last_ms = ms
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        res = self._lm.detect_for_video(self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb), ms)
        if not res.face_landmarks:
            return None
        return np.array([(p.x * w, p.y * h) for p in res.face_landmarks[0]], dtype=np.float64)

    def close(self) -> None:
        self._lm.close()

def polygon_mask(poly: np.ndarray, h: int, w: int) -> tuple[int, int, np.ndarray] | None:
    x0, x1 = max(int(np.floor(poly[:, 0].min())), 0), min(int(np.ceil(poly[:, 0].max())) + 1, w)
    y0, y1 = max(int(np.floor(poly[:, 1].min())), 0), min(int(np.ceil(poly[:, 1].max())) + 1, h)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None
    mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.fillPoly(mask, [np.round((poly - [x0, y0]) * 16).astype(np.int32)], 1, cv2.LINE_8, shift=4)
    return y0, x0, mask

def face_mask(pts: np.ndarray, h: int, w: int) -> tuple[int, int, np.ndarray] | None:
    geo = polygon_mask(pts[FACE_OVAL], h, w)
    if geo is None:
        return None
    y0, x0, mask = geo
    for idx in FACE_EXCLUDE:
        hull = cv2.convexHull(pts[idx].astype(np.float32)).reshape(-1, 2).astype(np.float64)
        c = hull.mean(axis=0)
        hull = c + EXCLUDE_GROW * (hull - c)
        cv2.fillPoly(mask, [np.round((hull - [x0, y0]) * 16).astype(np.int32)], 0, cv2.LINE_8, shift=4)
    return y0, x0, mask.astype(bool)

class SkinGate:
    def __init__(self):
        self.samples: deque = deque(maxlen=40)
        self.bounds: np.ndarray | None = None
        self.fits = 0
        self.last_fit = -1e9
        self.rng = np.random.default_rng(0)

    def observe(self, ycc_px: np.ndarray, now: float) -> None:
        if len(ycc_px) < 50:
            return
        self.samples.append(ycc_px[self.rng.choice(len(ycc_px), size=min(400, len(ycc_px)), replace=False)])
        if len(self.samples) >= 10 and now - self.last_fit >= (2.0 if self.fits < 5 else 30.0):
            px = np.concatenate(self.samples).astype(np.float64)
            y_min = 0.5 * float(np.median(px[:, 0]))
            px = px[px[:, 0] >= y_min]
            new = [y_min]
            for c in (1, 2):
                med = float(np.median(px[:, c]))
                half = max(3.0 * 1.4826 * float(np.median(np.abs(px[:, c] - med))), 8.0)
                new += [med - half, med + half]
            new = np.array(new)
            self.bounds = new if self.bounds is None else 0.7 * self.bounds + 0.3 * new
            self.fits += 1
            self.last_fit = now

    def select(self, ycc: np.ndarray, inside: np.ndarray) -> np.ndarray:
        y, cr, cb = ycc[..., 0], ycc[..., 1], ycc[..., 2]
        ok = inside & (y <= 250)
        if self.bounds is not None:
            b = self.bounds
            ok &= (y >= b[0]) & (cr >= b[1]) & (cr <= b[2]) & (cb >= b[3]) & (cb <= b[4])
        return ok

# ----------------------------------------------------------------------------- threads
def fourcc_str(v: float) -> str:
    i = int(v)
    return "".join(chr((i >> (8 * k)) & 0xFF) for k in range(4))

def raise_priority() -> None:
    if platform.system() == "Windows":
        try:
            k32 = ctypes.windll.kernel32
            k32.SetPriorityClass(k32.GetCurrentProcess(), 0x00000080)
            k32.SetThreadPriority(k32.GetCurrentThread(), 2)
        except Exception:
            pass

def tailnet_address() -> str | None:
    try:
        output = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        return output.splitlines()[0] if output else None
    except (OSError, subprocess.SubprocessError):
        return None

class Camera(threading.Thread):
    def __init__(self, args: argparse.Namespace, out: queue.Queue):
        super().__init__(name="camera", daemon=True)
        self.args, self.out = args, out
        self.ready, self.stop = threading.Event(), threading.Event()
        self.error: str | None = None
        self.dropped = 0
        self.t_recent: deque = deque(maxlen=61)
        self.fourcc = "?"

    def fps(self) -> float:
        t = list(self.t_recent)
        return (len(t) - 1) / (t[-1] - t[0]) if len(t) > 10 else float("nan")

    def run(self) -> None:
        a = self.args
        windows = platform.system() == "Windows"
        raise_priority()
        
        dev = a.camera
        if isinstance(dev, str) and dev.isdigit():
            dev = int(dev)
            
        backend = cv2.CAP_DSHOW if windows else cv2.CAP_V4L2 if platform.system() == "Linux" else cv2.CAP_ANY
        cap = cv2.VideoCapture(dev, backend)
        if not cap.isOpened() and backend != cv2.CAP_ANY:
            cap = cv2.VideoCapture(dev, cv2.CAP_ANY)

        try:
            if not cap.isOpened():
                raise RuntimeError(f"camera {dev} did not open")
            if windows:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUY2"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            ok, _ = cap.read()
            if not ok:
                raise RuntimeError(f"camera {dev} opened but returned no frame")
            self.fourcc = fourcc_str(cap.get(cv2.CAP_PROP_FOURCC))
            if str(a.exposure).lower() == "auto":
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
            else:
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
                cap.set(cv2.CAP_PROP_EXPOSURE, float(a.exposure))
            if a.wb > 0:
                cap.set(cv2.CAP_PROP_AUTO_WB, 0)
                cap.set(cv2.CAP_PROP_WB_TEMPERATURE, a.wb)
            cap.set(cv2.CAP_PROP_BACKLIGHT, 0)
            self.ready.set()
            while not self.stop.is_set():
                ok, frame = cap.read()
                t = time.perf_counter()
                if not ok:
                    raise RuntimeError("camera stopped delivering frames")
                self.t_recent.append(t)
                try:
                    self.out.put_nowait((frame, t))
                except queue.Full:
                    try:
                        self.out.get_nowait()
                        self.dropped += 1
                        self.out.put_nowait((frame, t))
                    except (queue.Empty, queue.Full):
                        pass
        except Exception as e:
            self.error = str(e)
            self.ready.set()
        finally:
            if cap.isOpened():
                cap.release()

class Processor(threading.Thread):
    def __init__(self, args: argparse.Namespace, frames: queue.Queue):
        super().__init__(name="processor", daemon=True)
        self.args, self.frames = args, frames
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.buf: deque = deque(maxlen=int(args.window * 45) + 300)
        self.view = None
        self.result: Result | None = None
        self.estimates: deque = deque(maxlen=3600)
        self.session: dict | None = None
        self.summary: dict | None = None
        self.t_proc: deque = deque(maxlen=61)
        self.centres: deque = deque(maxlen=90)
        self.error: str | None = None
        self.last_canvas: np.ndarray | None = None

        runs = Path(args.out) / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.run_log_path = runs / (datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv")
        self._run_file = open(self.run_log_path, "w", newline="")
        self._run_writer = csv.writer(self._run_file)
        self._run_writer.writerow([
            "clock", "time_s", "bpm", "snr_db", "chrom_bpm", "confident", "status", "hint",
            "face_skin_px", "face_green", "measuring",
        ])
        self._t_launch = time.perf_counter()

    def snapshot(self) -> dict:
        with self.lock:
            t = list(self.t_proc)
            return {
                "view": self.view,
                "result": self.result,
                "estimates": list(self.estimates)[-300:],
                "session": None if self.session is None else {
                    "t0": self.session["t0"],
                    "target_s": self.session["target_s"],
                    "rows": list(self.session["rows"]),
                },
                "summary": self.summary,
                "proc_fps": (len(t) - 1) / (t[-1] - t[0]) if len(t) > 10 else float("nan"),
            }

    def start_session(self, target_s: float) -> None:
        with self.lock:
            if self.session is not None:
                return
            path = Path(self.args.out) / datetime.now().strftime("%Y%m%d_%H%M%S")
            path.mkdir(parents=True, exist_ok=True)
            f = open(path / "hr_log.csv", "w", newline="")
            w = csv.writer(f)
            w.writerow([
                "time_s", "bpm", "snr_db", "chrom_bpm", "confident", "status", "hint",
                "face_skin_px", "face_green",
            ])
            self.session = {
                "path": path, "file": f, "writer": w, "t0": time.perf_counter(),
                "target_s": float(target_s), "samples": [], "rows": [],
            }
            self.summary = None
        print(f"measurement started ({target_s:.0f} s) -> {path}", flush=True)

    def stop_session(self, reason: str) -> None:
        with self.lock:
            s, self.session = self.session, None
        if s is not None:
            self._finish(s, reason)

    def finish_open_session(self) -> None:
        self.stop_session("window closed before the end")
        with self.lock:
            if not self._run_file.closed:
                self._run_file.close()

    def _finish(self, s: dict, reason: str) -> None:
        s["file"].close()
        rows = s["rows"]
        conf = [r["bpm"] for r in rows if r["confident"]]
        data = np.array(s["samples"], dtype=np.float64).reshape(-1, 6)
        whole = None
        if len(data) > 30:
            res, status = analyze_window(data[:, 0], data[:, 1:4], data[:, 4] > 0, data[-1, 0] - data[0, 0] + 1.0)
            whole = ({
                "bpm": round(res.bpm, 1), "snr_db": round(res.snr_db, 2), "chrom_bpm": round(res.chrom_bpm, 1),
                "confident": bool(res.confident), "analysed_s": round(res.window_s, 1),
            } if res is not None else {"status": status})
        summary = {
            "duration_s": round(time.perf_counter() - s["t0"], 1),
            "target_s": s["target_s"],
            "stopped": reason,
            "estimates": len(rows),
            "confident_pct": round(100.0 * len(conf) / max(len(rows), 1), 1),
            "median_bpm": round(float(np.median(conf)), 1) if conf else None,
            "whole_measurement": whole,
            "path": str(s["path"]),
        }
        np.savez_compressed(
            s["path"] / "traces.npz", t=data[:, 0] - s["t0"], rgb=data[:, 1:4],
            face_valid=data[:, 4] > 0, skin_px=data[:, 5],
        )
        (s["path"] / "summary.json").write_text(json.dumps({
            **summary, "window_s": self.args.window, "exposure": self.args.exposure, "white_balance_k": self.args.wb,
            "method": "POS headline, CHROM agreement check, SNR gate",
            "note": "wellness/research estimate, not a medical measurement",
        }, indent=2))
        with self.lock:
            self.summary = summary
        med = f"{summary['median_bpm']:.1f} bpm" if summary["median_bpm"] is not None else "no confident estimate"
        overall = f", {whole['bpm']:.1f} bpm over the whole interval" if whole and "bpm" in whole else ""
        print(f"measurement {reason}: {med} median over {summary['duration_s']:.0f} s{overall}, "
              f"{summary['confident_pct']:.0f} % confident -> {s['path']}", flush=True)

    def run(self) -> None:
        try:
            tracker = FaceTracker()
        except SystemExit as e:
            self.error = str(e)
            return
        gate, smoother = SkinGate(), OneEuroFilter()
        last_hr, n = 0.0, 0
        try:
            while not self.stop.is_set():
                try:
                    item = self.frames.get(timeout=0.5)
                except queue.Empty:
                    continue
                if item is None:
                    break
                frame, t = item
                h, w = frame.shape[:2]
                pts = tracker.track(frame, t)
                rgb, valid, px, geo, ok = (np.nan, np.nan, np.nan), False, 0, None, None
                if pts is None:
                    smoother.reset()
                else:
                    pts = smoother(pts, t)
                    self.centres.append((t, *pts.mean(axis=0), np.linalg.norm(pts[EYE_OUTER[0]] - pts[EYE_OUTER[1]])))
                    geo = face_mask(pts, h, w)
                    if geo is not None:
                        y0, x0, inside = geo
                        crop = frame[y0:y0 + inside.shape[0], x0:x0 + inside.shape[1]]
                        ycc = cv2.cvtColor(crop, cv2.COLOR_BGR2YCrCb)
                        if n % 10 == 0:
                            gate.observe(ycc[inside], t)
                        ok = gate.select(ycc, inside)
                        px = int(ok.sum())
                        if px >= MIN_SKIN_PX:
                            rgb, valid = tuple(crop[ok].mean(axis=0)[::-1]), True
                sample = (t, *rgb, float(valid), px)
                with self.lock:
                    self.buf.append(sample)
                    self.view = (frame, pts, geo, ok)
                    self.t_proc.append(t)
                    if self.session is not None:
                        self.session["samples"].append(sample)
                n += 1
                if t - last_hr >= 1.0:
                    last_hr = t
                    self._update_hr(t)
        except Exception as e:
            self.error = f"processing failed: {e}"
            raise
        finally:
            tracker.close()

    def _hint(self, now: float, recent: np.ndarray) -> str:
        face = recent[:, 4] > 0
        if len(recent) == 0 or face.mean() < 0.5:
            return "no face in view"
        if np.median(recent[face, 2]) < MIN_FACE_G:
            return "too dark: light on your face"
        c = np.array([x for x in self.centres if now - x[0] <= 1.0])
        if len(c) > 5 and np.max(np.linalg.norm(c[:, 1:3] - c[:, 1:3].mean(axis=0), axis=1)) > 0.08 * np.median(c[:, 3]):
            return "hold still"
        return ""

    def _update_hr(self, now: float) -> None:
        with self.lock:
            data = np.array(self.buf, dtype=np.float64)
        if len(data) < 30:
            return
        t, rgb, valid = data[:, 0], data[:, 1:4], data[:, 4] > 0
        result, status = analyze_window(t, rgb, valid, self.args.window)
        recent = data[t >= now - 1.0]
        face = recent[:, 4] > 0
        est = {
            "t": now,
            "bpm": result.bpm if result else float("nan"),
            "snr_db": result.snr_db if result else float("nan"),
            "chrom_bpm": result.chrom_bpm if result else float("nan"),
            "confident": bool(result and result.confident),
            "status": status,
            "hint": self._hint(now, recent),
            "face_px": float(np.median(recent[face, 5])) if face.any() else 0.0,
            "face_g": float(np.median(recent[face, 2])) if face.any() else float("nan"),
        }
        with self.lock:
            if result is not None:
                self.result = result
            self.estimates.append(est)
            s = self.session
            if not self._run_file.closed:
                self._run_writer.writerow([
                    datetime.now().strftime("%H:%M:%S"), f"{now - self._t_launch:.2f}",
                    f"{est['bpm']:.1f}", f"{est['snr_db']:.2f}", f"{est['chrom_bpm']:.1f}",
                    int(est["confident"]), est["status"], est["hint"], f"{est['face_px']:.0f}",
                    f"{est['face_g']:.1f}", int(s is not None),
                ])
                self._run_file.flush()
            if s is not None:
                s["rows"].append(est)
                s["writer"].writerow([
                    f"{now - s['t0']:.2f}", f"{est['bpm']:.1f}", f"{est['snr_db']:.2f}",
                    f"{est['chrom_bpm']:.1f}", int(est["confident"]), est["status"], est["hint"],
                    f"{est['face_px']:.0f}", f"{est['face_g']:.1f}",
                ])
                s["file"].flush()

# ----------------------------------------------------------------------------- drawing
def put(img: np.ndarray, text: str, org, scale: float, color, thick: int = 1) -> None:
    cv2.putText(img, text, (int(org[0]), int(org[1])), FONT, scale, color, thick, cv2.LINE_AA)

def text_width(text: str, scale: float, thick: int = 1) -> int:
    return cv2.getTextSize(text, FONT, scale, thick)[0][0]

def mmss(seconds: float) -> str:
    s = int(round(max(seconds, 0)))
    return f"{s // 60:02d}:{s % 60:02d}"

def length_label(seconds: float) -> str:
    return f"{seconds / 60:g} min" if seconds >= 60 and seconds % 60 == 0 else f"{seconds:.0f} s"

def draw_chart(img, rect, title, xlim, ylim, lines, xticks=(), yticks=(), xfmt="{:g}", yfmt="{:g}"):
    x0, y0, x1, y1 = rect
    cv2.rectangle(img, (x0, y0), (x1, y1), SURFACE, -1)
    put(img, title, (x0 + 14, y0 + 24), 0.52, INK2)
    ax0, ay0, ax1, ay1 = x0 + 46, y0 + 40, x1 - 16, y1 - 28

    def X(v):
        return ax0 + (np.asarray(v, dtype=np.float64) - xlim[0]) / (xlim[1] - xlim[0]) * (ax1 - ax0)

    def Y(v):
        return ay1 - (np.asarray(v, dtype=np.float64) - ylim[0]) / (ylim[1] - ylim[0]) * (ay1 - ay0)

    for yt in yticks:
        yy = int(Y(yt))
        cv2.line(img, (ax0, yy), (ax1, yy), GRID, 1)
        put(img, yfmt.format(yt), (x0 + 10, yy + 4), 0.4, MUTED)
    cv2.line(img, (ax0, ay1), (ax1, ay1), AXIS, 1)
    for xt in xticks:
        label = xfmt.format(xt)
        put(img, label, (X(xt) - text_width(label, 0.4) / 2, ay1 + 18), 0.4, MUTED)
    for xs, ys, color, thick in lines:
        xs, ys = np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64)
        idx = np.flatnonzero(np.isfinite(xs) & np.isfinite(ys))
        if len(idx) == 0:
            continue
        for run in np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1):
            p = np.column_stack([X(xs[run]), np.clip(Y(ys[run]), ay0, ay1)])
            if len(run) == 1:
                cv2.circle(img, (int(p[0, 0]), int(p[0, 1])), 2, color, -1, cv2.LINE_AA)
            else:
                cv2.polylines(img, [np.round(p * 16).astype(np.int32)], False, color, thick, cv2.LINE_AA, shift=4)
    return X, Y

def render(snap: dict, cam: Camera, args: argparse.Namespace, show_mask: bool,
           length_s: float) -> tuple[np.ndarray, dict]:
    canvas = np.full((CANVAS_H, 1280, 3), PAGE, np.uint8)
    estimates = snap["estimates"]
    latest = estimates[-1] if estimates else None
    res: Result | None = snap["result"]

    # camera view
    cv2.rectangle(canvas, (16, 16), (656, 496), SURFACE, -1)
    if snap["view"] is not None:
        frame, pts, geo, ok = snap["view"]
        fh, fw = frame.shape[:2]
        img = frame.copy() if (fh, fw) == (480, 640) else cv2.resize(frame, (640, 480))
        if show_mask and pts is not None:
            if geo is not None and ok is not None and (fh, fw) == (480, 640):
                y0, x0, inside = geo
                region = img[y0:y0 + inside.shape[0], x0:x0 + inside.shape[1]]
                region[ok] = (0.7 * region[ok] + 0.3 * np.array(GOOD)).astype(np.uint8)
            oval = pts[FACE_OVAL] * [640 / fw, 480 / fh]
            cv2.polylines(img, [np.round(oval * 16).astype(np.int32)], True, INK2, 1, cv2.LINE_AA, shift=4)
        canvas[16:496, 16:656] = img
    else:
        put(canvas, "starting camera ...", (40, 256), 0.8, INK2)
    cv2.rectangle(canvas, (16, 470), (656, 496), SURFACE, -1)
    put(canvas, "SPACE start/stop    + / - length    M skin overlay    Q quit", (28, 488), 0.45, MUTED)

    # status chip over the camera
    recent_conf = [e["bpm"] for e in estimates if e["confident"] and latest and latest["t"] - e["t"] <= 5.0]
    shown_bpm = float(np.median(recent_conf)) if recent_conf else None
    if latest is None:
        chip = (MUTED, "starting")
    elif latest["hint"]:
        chip = (BAD if latest["hint"].startswith("no face") else WARN, latest["hint"])
    elif not np.isfinite(latest["bpm"]):
        chip = (MUTED, latest["status"])
    elif latest["confident"] and shown_bpm is not None:
        chip = (GOOD, "good signal")
    else:
        chip = (WARN, "low confidence, keep still")
    tw = text_width(chip[1], 0.6)
    cv2.rectangle(canvas, (26, 26), (26 + tw + 44, 58), SURFACE, -1)
    cv2.circle(canvas, (44, 42), 7, chip[0], -1, cv2.LINE_AA)
    put(canvas, chip[1], (58, 48), 0.6, INK)

    # heart-rate block
    cv2.rectangle(canvas, (672, 16), (1264, 256), SURFACE, -1)
    put(canvas, "Heart rate (rPPG)", (696, 52), 0.7, INK2)
    if shown_bpm is not None:
        big, colour = f"{shown_bpm:.0f}", INK
    elif latest is not None and np.isfinite(latest["bpm"]):
        big, colour = f"{latest['bpm']:.0f}", MUTED
    else:
        big, colour = "--", MUTED
    cv2.putText(canvas, big, (692, 160), cv2.FONT_HERSHEY_DUPLEX, 3.6, colour, 5, cv2.LINE_AA)
    put(canvas, "bpm", (700 + cv2.getTextSize(big, cv2.FONT_HERSHEY_DUPLEX, 3.6, 5)[0][0], 160), 1.0, INK2, 2)
    cv2.circle(canvas, (704, 196), 7, chip[0], -1, cv2.LINE_AA)
    put(canvas, chip[1], (720, 202), 0.6, INK)
    if res is not None:
        put(canvas, f"SNR {res.snr_db:+.1f} dB   |   CHROM {res.chrom_bpm:.0f} bpm   |   {res.window_s:.0f} s window",
            (696, 230), 0.5, INK2)
    put(canvas, f"camera {cam.fps():.0f} fps   |   analysed {snap['proc_fps']:.0f} fps   |   dropped {cam.dropped}",
        (696, 248), 0.42, MUTED)

    # heart rate over time
    sess, summary = snap["session"], snap["summary"]
    if sess is not None:
        rows = sess["rows"]
        elapsed = time.perf_counter() - sess["t0"]
        xs = [r["t"] - sess["t0"] for r in rows]
        ys = [r["bpm"] if r["confident"] else np.nan for r in rows]
        conf = [y for y in ys if np.isfinite(y)]
        med = f"median {np.median(conf):.0f} bpm, {100 * len(conf) / max(len(rows), 1):.0f} % confident" if conf \
            else "no confident estimate yet"
        title = f"Measuring {mmss(elapsed)} / {mmss(sess['target_s'])}   {med}"
        xmax = max(sess["target_s"], elapsed, 10.0)
        step = 10 if xmax <= 60 else 30 if xmax <= 180 else 60
        xlim, xticks, xfmt = (0.0, xmax), np.arange(0, xmax + 1, step), "{:g}s"
    else:
        ref_t = latest["t"] if latest else time.perf_counter()
        sel = [e for e in estimates if ref_t - e["t"] <= 120]
        xs = [e["t"] - ref_t for e in sel]
        ys = [e["bpm"] if e["confident"] else np.nan for e in sel]
        if summary is not None:
            med = f"{summary['median_bpm']:.0f} bpm median" if summary["median_bpm"] is not None else "no confident estimate"
            title = f"Last measurement: {med}, {summary['duration_s']:.0f} s, {summary['confident_pct']:.0f} % confident (saved)"
        else:
            title = "Heart rate, last 2 minutes   (START below to measure)"
        xlim, xticks, xfmt = (-120.0, 0.0), (-120, -90, -60, -30, 0), "{:g}s"
    finite = [y for y in ys if np.isfinite(y)]
    lo = max(40, 10 * int(np.floor((min(finite) - 8) / 10))) if finite else 50
    hi = min(200, 10 * int(np.ceil((max(finite) + 8) / 10))) if finite else 110
    ystep = 10 if hi - lo <= 60 else 20
    draw_chart(canvas, (672, 264, 1264, 496), title, xlim, (lo, hi), [(xs, ys, SERIES, 2)],
               xticks=xticks, yticks=range(lo, hi + 1, ystep), xfmt=xfmt)

    # pulse waveform and spectrum
    if res is not None:
        k = res.tu >= res.tu[-1] - 10.0
        wave = res.pulse[k]
        scale = np.max(np.abs(wave)) or 1.0
        draw_chart(canvas, (16, 512, 656, 704), "Pulse (POS), last 10 s", (-10.0, 0.0), (-1.15, 1.15),
                   [(res.tu[k] - res.tu[-1], wave / scale, SERIES, 2)], xticks=(-10, -5, 0), xfmt="{:g}s")
        band = (res.f * 60 >= 40) & (res.f * 60 <= 200)
        p = res.psd[band] / (res.psd[band].max() or 1.0)
        X, Y = draw_chart(canvas, (672, 512, 1264, 704),
                          f"Spectrum (POS): peak {res.bpm:.0f} bpm, SNR {res.snr_db:+.1f} dB",
                          (40.0, 200.0), (0.0, 1.1), [(res.f[band] * 60, p, SERIES, 2)],
                          xticks=(60, 90, 120, 150, 180), xfmt="{:g}")
        cx, cy = int(X(res.bpm)), int(Y(1.0))
        cv2.circle(canvas, (cx, cy), 8, SURFACE, -1, cv2.LINE_AA)
        cv2.circle(canvas, (cx, cy), 6, SERIES, -1, cv2.LINE_AA)
    else:
        for rect, label in (((16, 512, 656, 704), "Pulse (POS)"), ((672, 512, 1264, 704), "Spectrum")):
            cv2.rectangle(canvas, rect[:2], rect[2:], SURFACE, -1)
            put(canvas, label, (rect[0] + 14, rect[1] + 24), 0.52, INK2)
            put(canvas, "waiting for a clean stretch of signal", (rect[0] + 14, rect[1] + 104), 0.55, MUTED)

    # measurement controls
    buttons: dict[str, tuple[int, int, int, int]] = {}
    running = sess is not None

    def button(name: str, rect: tuple[int, int, int, int], label: str, fill=None, selected: bool = False,
               enabled: bool = True) -> None:
        x0, y0, x1, y1 = rect
        if fill is not None or selected:
            cv2.rectangle(canvas, (x0, y0), (x1, y1), fill if fill is not None else SERIES, -1)
        else:
            cv2.rectangle(canvas, (x0, y0), (x1, y1), AXIS if enabled else GRID, 1)
        thick = 2 if fill is not None else 1
        colour = INK if (enabled or fill is not None) else MUTED
        put(canvas, label, ((x0 + x1 - text_width(label, 0.6, thick)) / 2, (y0 + y1) / 2 + 7), 0.6, colour, thick)
        if enabled:
            buttons[name] = rect

    cv2.rectangle(canvas, (16, 716), (1264, 784), SURFACE, -1)
    put(canvas, "Measure for", (32, 757), 0.6, INK2)
    shown_len = sess["target_s"] if running else length_s
    button("minus", (166, 730, 206, 770), "-", enabled=not running)
    value = f"{shown_len:.0f} s"
    put(canvas, value, ((210 + 300 - text_width(value, 0.7, 2)) / 2, 757), 0.7, INK, 2)
    button("plus", (304, 730, 344, 770), "+", enabled=not running)
    for i, p in enumerate(PRESETS_S):
        x = 366 + i * 82
        button(f"preset:{p}", (x, 730, x + 74, 770), length_label(p),
               selected=not running and abs(length_s - p) < 1e-6, enabled=not running)
    px0, px1 = 716, 1080
    if running:
        elapsed = time.perf_counter() - sess["t0"]
        frac = min(elapsed / sess["target_s"], 1.0)
        put(canvas, f"Recording {mmss(elapsed)} / {mmss(sess['target_s'])}   count your pulse", (px0, 746), 0.5, INK)
        cv2.rectangle(canvas, (px0, 758), (px1, 768), GRID, -1)
        cv2.rectangle(canvas, (px0, 758), (px0 + int(frac * (px1 - px0)), 768), SERIES, -1)
        button("stop", (1096, 726, 1248, 774), "STOP", fill=BAD)
        txt = f"REC  {mmss(sess['target_s'] - elapsed)} left"
        tw = text_width(txt, 0.6)
        cv2.rectangle(canvas, (646 - tw - 44, 26), (646, 58), SURFACE, -1)
        cv2.circle(canvas, (646 - tw - 26, 42), 7, BAD, -1, cv2.LINE_AA)
        put(canvas, txt, (646 - tw - 12, 48), 0.6, INK)
    else:
        if summary is not None:
            whole = summary.get("whole_measurement") or {}
            med = f"{summary['median_bpm']:.0f} bpm median" if summary["median_bpm"] is not None else "no confident reading"
            overall = f", {whole['bpm']:.0f} bpm overall" if "bpm" in whole else ""
            line1 = f"Last: {med}{overall}"
            line2 = f"{summary['confident_pct']:.0f} % confident, saved {Path(summary['path']).name}"
        else:
            line1 = "Pick a length, press START and count"
            line2 = "your pulse. It stops and saves by itself."
        put(canvas, line1, (px0, 746), 0.5, INK2)
        put(canvas, line2, (px0, 770), 0.45, MUTED)
        button("start", (1096, 726, 1248, 774), "START", fill=GOOD)
    return canvas, buttons

# ----------------------------------------------------------------------------- Web Server (Tailscale / HTTP)
class CanvasBroadcaster:
    def __init__(self):
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.jpeg: bytes | None = None
        self.vitals: dict = {}
        self.action_queue: queue.Queue[str] = queue.Queue(maxsize=32)

    def update(self, canvas: np.ndarray, latest_est: dict | None, res: Result | None):
        ok, buf = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            return
        with self.condition:
            self.jpeg = buf.tobytes()
            self.vitals = {
                "bpm": latest_est.get("bpm") if latest_est else None,
                "snr_db": latest_est.get("snr_db") if latest_est else None,
                "chrom_bpm": latest_est.get("chrom_bpm") if latest_est else None,
                "confident": latest_est.get("confident") if latest_est else False,
                "status": latest_est.get("status") if latest_est else "starting",
                "hint": latest_est.get("hint") if latest_est else "",
                "timestamp": time.time(),
            }
            self.condition.notify_all()

    def get_jpeg(self, timeout: float = 2.0) -> bytes | None:
        with self.condition:
            if self.jpeg is None:
                self.condition.wait(timeout)
            return self.jpeg

    def get_vitals(self) -> dict:
        with self.lock:
            return dict(self.vitals)

HTML_PAGE = """<!doctype html>
<html>
<head>
<title>MediKiosk Vitals &mdash; Heart Rate (rPPG)</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  html, body { margin:0; padding:0; background:#0d0d0d; color:#eee; font-family:system-ui, -apple-system, sans-serif; }
  header { background:#1a1a19; padding:12px 20px; border-bottom:1px solid #2c2c2a; display:flex; justify-content:space-between; align-items:center; }
  h1 { margin:0; font-size:18px; font-weight:600; color:#3987e5; }
  .controls { display:flex; gap:10px; margin:14px 20px; flex-wrap:wrap; }
  button { background:#1a1a19; color:#fff; border:1px solid #383835; padding:8px 16px; border-radius:6px; font-size:14px; cursor:pointer; font-weight:600; }
  button.start { background:#0ca30c; border-color:#0ca30c; }
  button.stop { background:#d03b3b; border-color:#d03b3b; }
  button:hover { opacity:0.9; }
  .container { display:flex; flex-direction:column; align-items:center; padding:10px; }
  img.stream { max-width:100%; border-radius:8px; box-shadow:0 8px 24px rgba(0,0,0,0.6); border:1px solid #2c2c2a; }
  .badge { background:#2c2c2a; padding:4px 10px; border-radius:12px; font-size:12px; color:#c3c2b7; }
</style>
</head>
<body>
<header>
  <h1>MediKiosk Live Camera Heart Rate (rPPG)</h1>
  <span class="badge">Tailscale Edge Vitals</span>
</header>
<div class="controls">
  <button class="start" onclick="fetch('/action?cmd=start')">START (60s)</button>
  <button class="stop" onclick="fetch('/action?cmd=stop')">STOP</button>
  <button onclick="fetch('/action?cmd=mask')">Toggle Skin Mask (M)</button>
  <button onclick="fetch('/action?cmd=preset_30')">30s</button>
  <button onclick="fetch('/action?cmd=preset_60')">60s</button>
  <button onclick="fetch('/action?cmd=preset_120')">120s</button>
</div>
<div class="container">
  <img class="stream" src="/stream.mjpg" alt="Heart Rate Canvas Stream">
</div>
</body>
</html>
"""

def make_web_handler(broadcaster: CanvasBroadcaster):
    class WebHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                body = HTML_PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/vitals":
                v = broadcaster.get_vitals()
                body = json.dumps(v).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/frame.jpg":
                jpg = broadcaster.get_jpeg()
                if jpg is None:
                    self.send_error(503, "No frame available")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpg)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(jpg)
            elif path == "/stream.mjpg":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=hrframe")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    while True:
                        jpg = broadcaster.get_jpeg()
                        if jpg is None:
                            time.sleep(0.05)
                            continue
                        self.wfile.write(b"--hrframe\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                        self.wfile.write(jpg)
                        self.wfile.write(b"\r\n")
                        time.sleep(0.033)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            elif path == "/action":
                query = self.path.split("?")[1] if "?" in self.path else ""
                cmd = query.replace("cmd=", "")
                if cmd:
                    try:
                        broadcaster.action_queue.put_nowait(cmd)
                    except queue.Full:
                        pass
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
            else:
                self.send_error(404)

    return WebHandler

# ----------------------------------------------------------------------------- self-test
def selftest() -> None:
    rng = np.random.default_rng(0)

    # 1. Vectorized POS matches Algorithm 1
    rgb = 100 + rng.normal(0, 1, (300, 3))
    l = int(np.ceil(1.6 * FS))
    ref = np.zeros(300)
    proj = np.array([[0, 1, -1], [-2, 1, 1]], dtype=np.float64)
    for m in range(300 - l + 1):
        s = (rgb[m:m + l] / rgb[m:m + l].mean(axis=0)) @ proj.T
        p = s[:, 0] + s[:, 0].std() / s[:, 1].std() * s[:, 1]
        ref[m:m + l] += p - p.mean()
    assert np.allclose(pos(rgb), ref), "vectorized POS differs from Algorithm 1"

    # 2. 72 bpm synthetic pulse with 114 bpm flicker
    n = int(20 * FS)
    t_true = np.arange(n) / FS
    pulse = np.sin(2 * np.pi * 1.2 * t_true) + 0.3 * np.sin(2 * np.pi * 2.4 * t_true + 0.5)
    pbv = np.array([0.33, 0.77, 0.53]) / 0.77
    light = (1 + 0.006 * np.sin(2 * np.pi * 1.9 * t_true)) * (1 + 0.03 * t_true / 20)
    skin = np.array([180.0, 130.0, 105.0])
    rgb = skin * (1 + 0.003 * np.outer(pulse, pbv)) * light[:, None] + rng.normal(0, 0.0005, (n, 3)) * skin
    t = np.maximum.accumulate(t_true + np.abs(rng.normal(0, 0.004, n))) + np.arange(n) * 1e-6
    res, status = analyze_window(t, rgb, np.ones(n, bool), 15.0)
    assert res is not None and abs(res.bpm - 72) < 2 and res.confident, (status, res and (res.bpm, res.snr_db))

    # 3. 30% brightness jump rejected
    rgb_jump = rgb.copy()
    rgb_jump[t > t[-1] - 4] *= 1.3
    res2, status2 = analyze_window(t, rgb_jump, np.ones(n, bool), 15.0)
    assert res2 is None and "light" in status2, status2

    # 4. Face missing in half the frames rejected
    valid = np.ones(n, bool)
    valid[::2] = False
    rgb_gap = rgb.copy()
    rgb_gap[~valid] = np.nan
    res3, status3 = analyze_window(t, rgb_gap, valid, 15.0)
    assert res3 is None and status3 == "face not found", status3

    # 5. Face mask geometry: eyes and mouth excluded, cheeks retained
    pts = np.zeros((478, 2))
    for idx, (cx, cy, r) in zip([FACE_OVAL, *FACE_EXCLUDE], [(320, 240, 150), (270, 200, 20), (370, 200, 20),
                                                              (320, 320, 25)]):
        a = np.linspace(0, 2 * np.pi, len(idx), endpoint=False)
        pts[idx] = np.column_stack([cx + r * np.cos(a), cy + r * np.sin(a)])
    y0, x0, m = face_mask(pts, 480, 640)
    full = np.zeros((480, 640), bool)
    full[y0:y0 + m.shape[0], x0:x0 + m.shape[1]] = m
    assert not full[200, 270] and not full[200, 370] and not full[320, 320] and full[280, 230]

    print(f"selftest passed: POS matches Algorithm 1; synthetic 72 bpm -> "
          f"{res.bpm:.1f} bpm (SNR {res.snr_db:+.1f} dB, CHROM {res.chrom_bpm:.1f}); "
          f"jump rejected ('{status2}'); face gaps rejected; face mask excludes eyes and mouth", flush=True)

# ----------------------------------------------------------------------------- main runner
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", default=0, help="Camera index (0, 1) or device path (/dev/video0)")
    ap.add_argument("--window", type=float, default=15.0, help="analysis window, s (10-30)")
    ap.add_argument("--measure", type=float, default=60.0, help="initial measurement length, s")
    ap.add_argument("--exposure", default="auto", help="'auto' or log2 value like -4")
    ap.add_argument("--wb", type=float, default=4600, help="white balance, K (0 = auto)")
    ap.add_argument("--out", default=str(REPO_ROOT / "data" / "live_sessions"), help="output directory")
    ap.add_argument("--duration", type=float, default=0, help="quit after N seconds (0 = forever)")
    ap.add_argument("--snapshot", default="", help="save last canvas to PNG on exit")
    ap.add_argument("--selftest", action="store_true", help="run synthetic test suite and exit")
    ap.add_argument("--web", action="store_true", help="enable web streaming over Tailscale/LAN")
    ap.add_argument("--port", type=int, default=8092, help="HTTP web port (default: 8092)")
    ap.add_argument("--host", default=None, help="host to bind HTTP (default: tailnet address or 0.0.0.0)")
    args = ap.parse_args(argv)

    if args.selftest:
        selftest()
        return 0

    sys.setswitchinterval(0.0005)
    frames: queue.Queue = queue.Queue(maxsize=8)
    cam = Camera(args, frames)
    cam.start()
    cam.ready.wait(15)
    if cam.error or not cam.ready.is_set():
        print(f"camera error: {cam.error or 'timed out opening camera'}", file=sys.stderr, flush=True)
        return 1

    proc = Processor(args, frames)
    proc.start()

    # Determine display / web mode
    broadcaster = CanvasBroadcaster()
    has_display = bool(os.environ.get("DISPLAY") or platform.system() == "Windows")
    force_web = args.web or not has_display
    
    server: ThreadingHTTPServer | None = None
    bind_host = args.host or tailnet_address() or "0.0.0.0"
    if force_web or args.web:
        try:
            server = ThreadingHTTPServer((bind_host, args.port), make_web_handler(broadcaster))
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            print(f"Heart rate streaming on: http://{bind_host}:{args.port}/", flush=True)
            print(f"  Stream: http://{bind_host}:{args.port}/stream.mjpg", flush=True)
            print(f"  Vitals: http://{bind_host}:{args.port}/api/vitals", flush=True)
        except Exception as e:
            print(f"could not start web stream on {bind_host}:{args.port}: {e}", flush=True)

    gui_active = False
    if not force_web:
        try:
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
            gui_active = True
        except cv2.error:
            gui_active = False

    clicks: list[tuple[int, int]] = []
    if gui_active:
        cv2.setMouseCallback(WINDOW_NAME, lambda event, x, y, flags, param:
                             clicks.append((x, y)) if event == cv2.EVENT_LBUTTONDOWN else None)

    show_mask, shown, t_start, canvas = True, False, time.monotonic(), None
    length_s = float(min(max(args.measure, 10.0), 600.0))
    last_toggle = -10.0

    print("Heart rate monitoring running... (Press Q or send stop to end)", flush=True)

    try:
        while True:
            if cam.error:
                print(f"camera error: {cam.error}", file=sys.stderr, flush=True)
                break
            if proc.error:
                print(f"processor error: {proc.error}", file=sys.stderr, flush=True)
                break

            snap = proc.snapshot()
            running = snap["session"] is not None
            if running and time.perf_counter() - snap["session"]["t0"] >= snap["session"]["target_s"]:
                proc.stop_session("completed")
                continue

            canvas, buttons = render(snap, cam, args, show_mask, length_s)
            broadcaster.update(canvas, snap["estimates"][-1] if snap["estimates"] else None, snap["result"])

            actions = []
            # Check web commands
            while not broadcaster.action_queue.empty():
                try:
                    cmd = broadcaster.action_queue.get_nowait()
                    if cmd == "start": actions.append("start")
                    elif cmd == "stop": actions.append("stop")
                    elif cmd == "mask": actions.append("mask")
                    elif cmd.startswith("preset_"): actions.append("preset:" + cmd.replace("preset_", ""))
                except queue.Empty:
                    break

            if gui_active:
                try:
                    cv2.imshow(WINDOW_NAME, canvas)
                    shown = True
                    key = cv2.waitKey(30) & 0xFF
                    if key in (ord("q"), 27):
                        break
                    if shown and cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                        break
                    actions += [name for x, y in clicks for name, (x0, y0, x1, y1) in buttons.items()
                                if x0 <= x <= x1 and y0 <= y <= y1]
                    clicks.clear()
                    if key == ord(" "):
                        actions.append("stop" if running else "start")
                    elif key in (ord("+"), ord("=")):
                        actions.append("plus")
                    elif key in (ord("-"), ord("_")):
                        actions.append("minus")
                    elif key == ord("m"):
                        actions.append("mask")
                except cv2.error:
                    gui_active = False
            else:
                time.sleep(0.05)

            for action in actions:
                debounced = time.monotonic() - last_toggle >= 1.5
                if action == "start" and not running and debounced:
                    proc.start_session(length_s)
                    running, last_toggle = True, time.monotonic()
                elif action == "stop" and running and debounced:
                    proc.stop_session("stopped early")
                    running, last_toggle = False, time.monotonic()
                elif not running and action == "plus":
                    length_s = min(length_s + 10.0, 600.0)
                elif not running and action == "minus":
                    length_s = max(length_s - 10.0, 10.0)
                elif not running and action.startswith("preset:"):
                    length_s = float(action.split(":")[1])
                elif action == "mask":
                    show_mask = not show_mask

            if args.duration and time.monotonic() - t_start >= args.duration:
                break
    finally:
        cam.stop.set()
        cam.join(timeout=5)
        proc.stop.set()
        try:
            frames.put_nowait(None)
        except queue.Full:
            pass
        proc.join(timeout=10)
        proc.finish_open_session()
        if server is not None:
            server.shutdown()
        if args.snapshot and canvas is not None:
            cv2.imwrite(args.snapshot, canvas)
            print(f"snapshot saved: {args.snapshot}", flush=True)
        if gui_active:
            cv2.destroyAllWindows()

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
