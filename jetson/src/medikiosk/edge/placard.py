"""Hold the kiosk's address on the 2.8" panel.

The panel is otherwise driven by the intake loop, one patient screen at a time. On a demo table it
has a second job: say - with no laptop present - what address the tablet should be pointed at. When
the tablet is plugged in and sharing its connection over USB, the tablet's DHCP decides what this
board's address is, and this screen is the only place anyone can read it.

    python3 -m medikiosk.edge.placard                 # show it and hold
    python3 -m medikiosk.edge.placard --png out.png   # render only, no panel needed

Run it under system python: the panel needs spidev and Jetson.GPIO, which the audio venv has not.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 320, 240

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



def render(scale: int = 1, addresses: list[str] | None = None) -> Image.Image:
    """The card, at `scale` for inspection on a normal screen."""

    image = Image.new("RGB", (WIDTH * scale, HEIGHT * scale), BACKGROUND)
    draw = ImageDraw.Draw(image)
    label_font = _font(FONT_PATH, 9 * scale)
    title_font = _font(FONT_BOLD, 13 * scale)
    # The address is the reason this screen exists, and it gets read from across a table by someone
    # typing it into a tablet. On a 320px panel that is worth most of the space now going spare.
    address_font = _font(FONT_BOLD, 17 * scale)
    margin = 8 * scale

    draw.rectangle(
        [(margin // 2, margin // 2), (image.width - margin // 2, image.height - margin // 2)],
        outline=RULE,
        width=max(1, scale),
    )

    lines = (addresses if addresses is not None else _addresses()) or ["waiting for a network"]

    # One block, centred: with nothing else on the card, a footer-pinned address sits under an
    # expanse of empty panel and reads like something failed to draw.
    block = int(19 * scale) + int(11 * scale) + int(14 * scale) + int(21 * scale) * len(lines)
    y = max(margin + 2 * scale, (image.height - block) // 2)

    draw.text((margin, y), "MEDIKIOSK", font=title_font, fill=INK)
    y += int(19 * scale)
    draw.line([(margin, y), (image.width - margin, y)], fill=RULE)
    y += int(11 * scale)
    draw.text((margin, y), "KIOSK ADDRESS  PORT 8000", font=label_font, fill=LABEL_INK)
    y += int(14 * scale)
    for line in lines:
        draw.text((margin, y), line, font=address_font, fill=ADDRESS_INK)
        y += int(21 * scale)
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

    # Redraw only when the addresses change: pushing 320x240 over SPI every few seconds for an
    # identical image is wasted power on a battery-run table.
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
