"""Read the camera continuously, so a document can be aimed and checked in real time.

The recognizer takes about two seconds a frame on this board, so this is not video-rate OCR: it
reads the newest frame, reports what it found, and reads again. That is exactly what is needed for
aiming - hold the prescription up, watch the line count rise, stop moving when it peaks.

Also the practical way to find this camera's focus, since its autofocus does not move the lens:
run with --sweep-focus and the reading itself scores each lens position.

    scripts/kiosk live_ocr                       # read until interrupted
    scripts/kiosk live_ocr --focus 750 --panel   # fixed focus, mirror on the LCD
    scripts/kiosk live_ocr --sweep-focus         # find the focus for this distance
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent

FOCUS_POSITIONS = [1, 120, 240, 360, 480, 600, 750, 900, 1023]


def set_focus(device: str, value: int) -> None:
    subprocess.run(
        ["v4l2-ctl", "-d", device, "--set-ctrl", "focus_automatic_continuous=0"],
        capture_output=True,
    )
    subprocess.run(
        ["v4l2-ctl", "-d", device, "--set-ctrl", f"focus_absolute={value}"], capture_output=True
    )


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="/dev/video0")
    parser.add_argument("--size", default="1600x1200")
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--focus", type=int, default=None)
    parser.add_argument("--sweep-focus", action="store_true")
    parser.add_argument("--panel", action="store_true", help="mirror the frame on the LCD")
    parser.add_argument("--seconds", type=float, default=0.0, help="stop after this long")
    parser.add_argument("--show", type=int, default=3, help="lines of text to print per read")
    args = parser.parse_args(argv)

    from medikiosk.edge.camera import FrameSource
    from ocr.models.adapters import PPOcrOnnx

    model = PPOcrOnnx(str(REPO / "offline/jetson/models/ppocr_onnx"))
    started = time.monotonic()
    model.load()
    print(f"recognizer ready in {time.monotonic() - started:.1f}s", flush=True)

    panel = None
    if args.panel:
        try:
            from medikiosk.edge.panel import KioskPanel

            panel = KioskPanel()
            panel.open()
        except Exception as error:
            print(f"panel unavailable: {type(error).__name__}: {error}")

    if args.focus is not None:
        set_focus(args.device, args.focus)

    source = FrameSource(args.device, args.size, args.fps)
    source.start()
    print("reading... (ctrl-c to stop)", flush=True)

    frame_path = Path("/tmp/live_ocr_frame.jpg")
    positions = list(FOCUS_POSITIONS) if args.sweep_focus else []
    best: tuple[int, int] | None = None
    deadline = started + args.seconds if args.seconds else None

    try:
        while True:
            if deadline and time.monotonic() > deadline:
                break
            if args.sweep_focus:
                if not positions:
                    break
                position = positions.pop(0)
                set_focus(args.device, position)
                time.sleep(0.8)  # let the lens travel and a fresh frame arrive

            frame = source.latest()
            if frame is None:
                print("camera stopped delivering frames")
                break
            frame_path.write_bytes(frame)

            began = time.monotonic()
            text = model.recognize(frame_path)
            elapsed = time.monotonic() - began
            lines = [line for line in text.splitlines() if line.strip()]

            label = f"focus {position:5}" if args.sweep_focus else time.strftime("%H:%M:%S")
            print(f"{label}  {elapsed:4.1f}s  {len(lines):3} line(s)", flush=True)
            for line in lines[: args.show]:
                print(f"      {line}", flush=True)

            if args.sweep_focus and (best is None or len(lines) > best[1]):
                best = (position, len(lines))

            if panel is not None:
                try:
                    from PIL import Image

                    panel.show(Image.open(io.BytesIO(frame)))
                except Exception:
                    panel = None  # a dead screen must not stop the reading
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        source.stop()
        if panel is not None:
            panel.close()

    if args.sweep_focus and best:
        print(f"\nbest focus {best[0]} with {best[1]} line(s)")
        print(f"use it with: scripts/kiosk live_ocr --focus {best[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
