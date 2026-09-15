"""Photograph a document with the kiosk camera and read it.

This is the document-capture path in miniature: one frame at the sensor's full resolution, then
the on-device OCR. Resolution matters more here than anywhere else in the kiosk - a prescription
photographed at 720p loses the dose digits that a physician needs.

    scripts/kiosk capture                       # capture and read
    scripts/kiosk capture --panel               # also show the frame on the LCD
    scripts/kiosk capture --keep /tmp/rx.jpg    # keep the photograph
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent

# The sensor's largest MJPEG mode. Small print on a prescription does not survive 720p.
FULL_RESOLUTION = "3264x2448"


def set_focus(device: str, value: int | None) -> None:
    """Park the lens at a fixed distance.

    Continuous autofocus is advertised by this camera but does not move the lens - the reported
    focus_absolute stays put through seconds of streaming - so the kiosk sets focus explicitly for
    its fixed document distance instead of trusting AF.
    """

    if value is None:
        return
    subprocess.run(
        ["v4l2-ctl", "-d", device, "--set-ctrl", "focus_automatic_continuous=0"],
        capture_output=True,
    )
    subprocess.run(
        ["v4l2-ctl", "-d", device, "--set-ctrl", f"focus_absolute={value}"],
        capture_output=True,
    )
    time.sleep(0.6)  # the lens takes a moment to travel


def grab(device: str, size: str, target: Path, warmup: int = 6) -> None:
    """Take one frame. The first frames after opening are dark while exposure settles."""

    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "v4l2",
            "-input_format", "mjpeg",
            "-video_size", size,
            "-i", device,
            "-frames:v", str(warmup),
            "-update", "1",
            "-y",
            str(target),
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not target.exists():
        detail = result.stderr.decode("utf-8", "replace").strip()[-300:]
        raise RuntimeError(
            f"could not capture from {device}: {detail}\n"
            "If the preview server is running it holds the camera: pkill -f medikiosk.edge.camera"
        )


def read_lines(photo: Path) -> list[str]:
    from ocr.models.adapters import PPOcrOnnx

    model = PPOcrOnnx(str(REPO / "offline/jetson/models/ppocr_onnx"))
    model.load()
    text = model.recognize(photo)
    model.unload()
    return [line for line in text.splitlines() if line.strip()]


def sweep(args) -> int:
    """Pick a lens position by what the OCR actually reads, not by a sharpness proxy.

    Whole-frame sharpness is dominated by background clutter in a real room; the number of lines
    recognised on the document is the measure that matters.
    """

    positions = [1, 120, 240, 360, 480, 600, 750, 900, 1023]
    best: tuple[int, int, Path] | None = None
    workdir = Path(tempfile.mkdtemp(prefix="sweep-"))
    for position in positions:
        set_focus(args.device, position)
        photo = workdir / f"focus_{position:04d}.jpg"
        grab(args.device, args.size, photo)
        lines = read_lines(photo)
        print(f"focus {position:5}  {len(lines):3} line(s)")
        if best is None or len(lines) > best[1]:
            best = (position, len(lines), photo)
    assert best is not None
    print()
    print(f"best: focus {best[0]} with {best[1]} line(s) -> {best[2]}")
    if best[1] == 0:
        print(
            "No position read any text. Hold a document flat, filling the frame, well lit, "
            "roughly 15-25 cm from the lens, and run the sweep again."
        )
    else:
        print(f"Keep it with: scripts/kiosk capture --focus {best[0]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="/dev/video0")
    parser.add_argument("--size", default=FULL_RESOLUTION)
    parser.add_argument("--keep", type=Path, default=None, help="save the photograph here")
    parser.add_argument("--panel", action="store_true", help="show the frame on the LCD")
    parser.add_argument("--no-ocr", action="store_true", help="capture only")
    parser.add_argument("--focus", type=int, default=None, help="lens position, 1-1023")
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="try a range of focus positions and keep the one the OCR reads best",
    )
    args = parser.parse_args(argv)

    if args.sweep:
        return sweep(args)

    workdir = tempfile.mkdtemp(prefix="capture-")
    photo = args.keep or Path(workdir) / "capture.jpg"
    photo.parent.mkdir(parents=True, exist_ok=True)

    set_focus(args.device, args.focus)
    started = time.monotonic()
    grab(args.device, args.size, photo)
    print(f"captured {args.size} in {time.monotonic() - started:.2f}s -> {photo}")

    if args.panel:
        try:
            from PIL import Image

            from medikiosk.edge.panel import KioskPanel

            panel = KioskPanel()
            panel.open()
            panel.show(Image.open(photo))
            panel.close()
            print("shown on panel")
        except Exception as error:
            print(f"panel unavailable: {type(error).__name__}: {error}")

    if args.no_ocr:
        return 0

    from ocr.models.adapters import PPOcrOnnx

    model = PPOcrOnnx(str(REPO / "offline/jetson/models/ppocr_onnx"))
    started = time.monotonic()
    model.load()
    loaded = time.monotonic() - started

    started = time.monotonic()
    text = model.recognize(photo)
    elapsed = time.monotonic() - started

    lines = [line for line in text.splitlines() if line.strip()]
    print(f"model load {loaded:.2f}s, read {elapsed:.2f}s, {len(lines)} line(s)")
    print("-" * 60)
    for line in lines:
        print(line)
    if not lines:
        print("(nothing readable - is a document in front of the camera, lit and in focus?)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
