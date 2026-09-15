from __future__ import annotations

import numpy as np
import pytest

from medikiosk.edge.heart_rate import (
    CanvasBroadcaster,
    FACE_EXCLUDE,
    FACE_OVAL,
    FS,
    analyze_window,
    bandpass,
    detrend_ratio,
    face_mask,
    pos,
    selftest,
)


def test_selftest_passes():
    """Built-in selftest must run without error."""
    selftest()


def test_pos_algorithm_matches_vectorized():
    """Vectorized POS implementation matches explicit Wang et al. 2017 Alg 1."""
    rng = np.random.default_rng(42)
    rgb = 120.0 + rng.normal(0, 1, (300, 3))
    l = int(np.ceil(1.6 * FS))
    ref = np.zeros(300)
    proj = np.array([[0, 1, -1], [-2, 1, 1]], dtype=np.float64)
    for m in range(300 - l + 1):
        s = (rgb[m:m + l] / rgb[m:m + l].mean(axis=0)) @ proj.T
        p = s[:, 0] + s[:, 0].std() / s[:, 1].std() * s[:, 1]
        ref[m:m + l] += p - p.mean()

    assert np.allclose(pos(rgb), ref, atol=1e-8)


def test_synthetic_hr_extraction():
    """72 bpm pulse with 114 bpm flicker extracted with SNR > 0 dB and high confidence."""
    rng = np.random.default_rng(101)
    n = int(20 * FS)
    t_true = np.arange(n) / FS
    pulse = np.sin(2 * np.pi * 1.2 * t_true) + 0.3 * np.sin(2 * np.pi * 2.4 * t_true + 0.5)
    pbv = np.array([0.33, 0.77, 0.53]) / 0.77
    light = (1 + 0.006 * np.sin(2 * np.pi * 1.9 * t_true)) * (1 + 0.03 * t_true / 20)
    skin = np.array([180.0, 130.0, 105.0])
    rgb = skin * (1 + 0.003 * np.outer(pulse, pbv)) * light[:, None] + rng.normal(0, 0.0005, (n, 3)) * skin
    t = np.maximum.accumulate(t_true + np.abs(rng.normal(0, 0.004, n))) + np.arange(n) * 1e-6

    res, status = analyze_window(t, rgb, np.ones(n, bool), 15.0)
    assert res is not None
    assert status == "ok"
    assert abs(res.bpm - 72.0) < 2.0
    assert res.confident is True
    assert res.snr_db > 0.0


def test_brightness_jump_rejection():
    """Sudden 30% brightness jump cuts signal, rejecting contaminated stretch."""
    rng = np.random.default_rng(7)
    n = int(20 * FS)
    t = np.arange(n) / FS
    rgb = 100.0 + rng.normal(0, 1, (n, 3))
    # Jump 3 seconds before the end
    rgb[t > t[-1] - 3] *= 1.35
    res, status = analyze_window(t, rgb, np.ones(n, bool), 15.0)
    assert res is None
    assert "light" in status or "settling" in status


def test_face_gaps_rejection():
    """Face missing in more than 20% of frames is rejected."""
    n = int(20 * FS)
    t = np.arange(n) / FS
    rgb = np.ones((n, 3)) * 120.0
    valid = np.ones(n, bool)
    valid[::3] = False  # 33% missing
    rgb[~valid] = np.nan
    res, status = analyze_window(t, rgb, valid, 15.0)
    assert res is None
    assert status == "face not found"


def test_face_mask_geometry():
    """Face mask geometry retains cheeks and carves out eyes and mouth."""
    pts = np.zeros((478, 2))
    for idx, (cx, cy, r) in zip(
        [FACE_OVAL, *FACE_EXCLUDE],
        [(320, 240, 150), (270, 200, 20), (370, 200, 20), (320, 320, 25)],
    ):
        a = np.linspace(0, 2 * np.pi, len(idx), endpoint=False)
        pts[idx] = np.column_stack([cx + r * np.cos(a), cy + r * np.sin(a)])

    y0, x0, m = face_mask(pts, 480, 640)
    full = np.zeros((480, 640), bool)
    full[y0 : y0 + m.shape[0], x0 : x0 + m.shape[1]] = m

    # Right eye center excluded
    assert not full[200, 270]
    # Left eye center excluded
    assert not full[200, 370]
    # Mouth center excluded
    assert not full[320, 320]
    # Cheek included
    assert full[280, 230]


def test_canvas_broadcaster_vitals():
    """CanvasBroadcaster safely receives updates and formats /api/vitals."""
    broadcaster = CanvasBroadcaster()
    canvas = np.zeros((100, 100, 3), dtype=np.uint8)
    broadcaster.update(
        canvas,
        latest_est={
            "bpm": 74.5,
            "snr_db": 6.2,
            "chrom_bpm": 74.1,
            "confident": True,
            "status": "ok",
            "hint": "",
        },
        res=None,
    )

    v = broadcaster.get_vitals()
    assert v["bpm"] == 74.5
    assert v["confident"] is True
    assert v["status"] == "ok"
    assert broadcaster.get_jpeg() is not None
