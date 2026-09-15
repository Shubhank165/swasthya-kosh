#!/usr/bin/env python3
"""Standalone runner for live camera heart rate (rPPG), end to end.

Usage:
    python heart_rate_end_to_end.py              # open the live window or stream over Tailscale
    python heart_rate_end_to_end.py --selftest   # check signal maths on synthetic data
    python heart_rate_end_to_end.py --web        # force web streaming mode
"""
import sys
from pathlib import Path

# Ensure src/ is on sys.path so medikiosk modules can be imported
HERE = Path(__file__).resolve().parent
SRC_DIR = HERE / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from medikiosk.edge.heart_rate import main, selftest

if __name__ == "__main__":
    raise SystemExit(main())
