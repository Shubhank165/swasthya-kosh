"""Hold the team's entry details, and the kiosk's address, on the 2.8" panel.

The panel is otherwise driven by the intake loop, one patient screen at a time. On a demo table it
has a second job: say which entry this hardware belongs to, and - with no laptop present - what
address the tablet should be pointed at. When the tablet is plugged in and sharing its connection
over USB, the tablet's DHCP decides what this board's address is, and this screen is the only
place anyone can read it.

    python3 -m medikiosk.edge.placard                 # show it and hold
    python3 -m medikiosk.edge.placard --png out.png   # render only, no panel needed

Run it under system python: the panel needs spidev and Jetson.GPIO, which the audio venv has not.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 320, 240

# The entry details are competition paperwork, not product configuration: they name a team and a
# submission, they change per event, and they have no business being in a public repository. So they
# live in a JSON file on the board that renders them, and this module only knows how to find one.
#
#     [["Team Name", "..."], ["Track", "..."]]
#
# A list of [label, value] pairs, rendered top to bottom in the order given. Point
# MEDIKIOSK_PLACARD_ENTRY at a file, or drop one at the default path below. With no file present the
# placeholder renders, which keeps `--png` working on a fresh clone.
ENTRY_ENV = "MEDIKIOSK_PLACARD_ENTRY"
ENTRY_PATH = Path.home() / ".config" / "medikiosk" / "placard.json"

PLACEHOLDER: tuple[tuple[str, str], ...] = (
    ("Project", "MediKiosk"),
    ("Role", "Clinical intake kiosk"),
)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
INK = (14, 22, 38)
LABEL_INK = (108, 122, 148)
BACKGROUND = (248, 250, 253)
RULE = (214, 224, 238)
ADDRESS_INK = (12, 92, 62)

# Interfaces worth showing, in the order a demo would use them. A USB tether appears as its own
# interface whose name the kernel picks, so anything usb-shaped is matched by prefix.
WIRED_PREFIXES = ("usb", "enx", "eth", "rndis")



def _entry() -> tuple[tuple[str, str], ...]:
    """The entry details, or the placeholder if no file is installed.

    A malformed file is worth a word on stderr rather than a traceback: the placard runs headless
    under systemd on a demo table, and a crash there means a blank panel with nobody watching a log.
    """

    path = Path(os.environ[ENTRY_ENV]) if os.environ.get(ENTRY_ENV) else ENTRY_PATH
    if not path.is_file():
        return PLACEHOLDER
    try:
        loaded = json.loads(path.read_text())
        return tuple((str(label), str(value)) for label, value in loaded)
    except (OSError, ValueError, TypeError) as exc:
        print(f"placard: ignoring {path}: {exc}", file=sys.stderr)
        return PLACEHOLDER


def _addresses() -> list[str]:
    """Every usable IPv4 address this board answers on, most useful first.

    Reading them at draw time rather than at start-up is the whole point: the tether interface
    does not exist until the tablet is plugged in and sharing, which is after this is running.
    """

    found: list[tuple[str, str]] = []
    try:
        output = subprocess.run(
            ["ip", "-4", "-oneline", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        name, address = parts[1], parts[3].split("/")[0]
        if name == "lo" or address.startswith("127."):
            continue
        found.append((name, address))

    def rank(item: tuple[str, str]) -> int:
        name = item[0]
        if name.startswith(WIRED_PREFIXES):
            return 0  # the USB path, which is what the tablet will be using
        if name.startswith("wl"):
            return 1
        return 2

    found.sort(key=rank)
    return [f"{name}  {address}" for name, address in found]


def _font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        # A missing font must still produce a readable card rather than no card at all.
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render(scale: int = 1, addresses: list[str] | None = None) -> Image.Image:
    """The card, at `scale` for inspection on a normal screen."""

    image = Image.new("RGB", (WIDTH * scale, HEIGHT * scale), BACKGROUND)
    draw = ImageDraw.Draw(image)
    label_font = _font(FONT_PATH, 8 * scale)
    value_font = _font(FONT_BOLD, 12 * scale)
    address_font = _font(FONT_BOLD, 9 * scale)
    margin = 8 * scale
    inner = image.width - margin * 2

    draw.rectangle(
        [(margin // 2, margin // 2), (image.width - margin // 2, image.height - margin // 2)],
        outline=RULE,
        width=max(1, scale),
    )

    y = margin + 2 * scale
    for label, value in _entry():
        draw.text((margin, y), label.upper(), font=label_font, fill=LABEL_INK)
        y += int(10 * scale)
        for line in _wrap(draw, value, value_font, inner):
            draw.text((margin, y), line, font=value_font, fill=INK)
            y += int(14 * scale)
        y += int(2 * scale)

    lines = addresses if addresses is not None else _addresses()
    footer = image.height - margin - int(11 * scale) * max(1, len(lines))
    draw.line([(margin, footer - 5 * scale), (image.width - margin, footer - 5 * scale)], fill=RULE)
    draw.text((margin, footer - int(14 * scale)), "KIOSK ADDRESS  PORT 8000", font=label_font, fill=LABEL_INK)
    for line in lines or ["waiting for a network"]:
        draw.text((margin, footer), line, font=address_font, fill=ADDRESS_INK)
        footer += int(11 * scale)
    return image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--png", type=Path, help="write the card to a PNG instead of the panel")
    parser.add_argument("--scale", type=int, default=1, help="upscale for --png")
    args = parser.parse_args(argv)

    if args.png:
        render(args.scale).save(args.png)
        print(f"wrote {args.png}")
        return 0

    from medikiosk.edge.panel import KioskPanel

    panel = KioskPanel()
    panel.open()

    # Redraw only when the addresses change: the entry details never do, and pushing 320x240 over
    # SPI every few seconds for an identical image is wasted power on a battery-run table.
    shown: list[str] | None = None
    try:
        while True:
            current = _addresses()
            if current != shown:
                panel.show(render(addresses=current))
                shown = current
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        panel.backlight(False)
        panel.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
