"""The 2.8" ILI9341 kiosk panel, driven over hardware SPI.

Pin names are Tegra SoC names, not BOARD numbers, and they come from the wiring this board was
built with (the PocketInfer devboard): the display sits on SPI1 CS0 with the XPT2046 touch
controller sharing the bus on CS1.

Adafruit Blinka is already installed on this device and its ILI9341 driver accepts a PIL image
directly, which is exactly what medikiosk.edge.display renders. That avoids a hand-rolled spidev
driver and matches the stack this panel is known to work with.

    scripts/kiosk panel --test-pattern
    scripts/kiosk panel --image /tmp/screens/screen_hi.png
    scripts/kiosk panel --screen ask_complaint --language hi
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

WIDTH, HEIGHT = 320, 240


@dataclass(frozen=True)
class PanelPins:
    """Wiring of the panel. Defaults are this board's; override only if the harness changes."""

    reset: str = "GP36_SPI3_CLK"
    backlight: str = "GP122"
    chip_select: str = "GP50_SPI1_CS0_N"
    data_command: str = "GP88_PWM1"
    touch_cs: str = "GP51_SPI1_CS1_N"
    touch_irq: str = "GP37_SPI3_MISO"
    baudrate: int = 30_000_000
    rotation: int = 90


class KioskPanel:
    def __init__(self, pins: PanelPins | None = None) -> None:
        self.pins = pins or PanelPins()
        self.display = None
        self._backlight = None

    def open(self) -> None:
        import board
        import digitalio
        from adafruit_rgb_display import ili9341

        spi = board.SPI()
        reset = digitalio.DigitalInOut(board.pin.Pin(self.pins.reset))
        chip_select = digitalio.DigitalInOut(board.pin.Pin(self.pins.chip_select))
        data_command = digitalio.DigitalInOut(board.pin.Pin(self.pins.data_command))

        self._backlight = digitalio.DigitalInOut(board.pin.Pin(self.pins.backlight))
        self._backlight.direction = digitalio.Direction.OUTPUT
        self._backlight.value = True

        self.display = ili9341.ILI9341(
            spi,
            cs=chip_select,
            dc=data_command,
            rst=reset,
            baudrate=self.pins.baudrate,
            width=WIDTH,
            height=HEIGHT,
            rotation=self.pins.rotation,
        )

    def show(self, image) -> None:
        """Blit a PIL image, sized to whatever the driver reports.

        With rotation applied the driver's width and height are not the constructor's, so ask it
        rather than assuming: a mismatch is refused outright, not scaled silently.
        """

        from PIL import Image

        assert self.display is not None
        target = (self.display.width, self.display.height)
        if image.size != target:
            image = image.resize(target, Image.LANCZOS)
        # rotation=0 because the panel is already in landscape: the controller's MADCTL was set
        # from the constructor's rotation at init. Letting the library rotate again would turn a
        # 320x240 image into 240x320 and fail its own bounds check.
        self.display.image(image.convert("RGB"), rotation=0)

    def backlight(self, on: bool) -> None:
        if self._backlight is not None:
            self._backlight.value = on

    def close(self) -> None:
        # Leave the backlight on: a kiosk that blanks between frames looks broken to a patient.
        self.display = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=None, help="show a PNG")
    parser.add_argument("--screen", default=None, help="render a question id and show it")
    parser.add_argument("--language", default="hi")
    parser.add_argument("--test-pattern", action="store_true")
    parser.add_argument("--backlight-off", action="store_true")
    parser.add_argument("--rotation", type=int, default=None)
    parser.add_argument("--baudrate", type=int, default=None)
    args = parser.parse_args(argv)

    pins = PanelPins()
    if args.rotation is not None or args.baudrate is not None:
        pins = PanelPins(
            rotation=args.rotation if args.rotation is not None else pins.rotation,
            baudrate=args.baudrate if args.baudrate is not None else pins.baudrate,
        )

    panel = KioskPanel(pins)
    panel.open()

    from PIL import Image, ImageDraw

    if args.backlight_off:
        panel.backlight(False)
        print("backlight off")
        return 0

    if args.image:
        panel.show(Image.open(args.image))
        print(f"showed {args.image}")
    elif args.screen:
        from medikiosk.edge.display import question_screen, render

        panel.show(render(question_screen(args.screen, args.language, step=(1, 7))))
        print(f"showed {args.screen} in {args.language}")
    else:
        image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        bars = [(220, 40, 40), (40, 200, 90), (60, 120, 240), (240, 240, 240)]
        for index, colour in enumerate(bars):
            draw.rectangle(
                [index * WIDTH // 4, 0, (index + 1) * WIDTH // 4, HEIGHT], fill=colour
            )
        draw.text((10, HEIGHT - 20), "MediKiosk panel test", fill=(0, 0, 0))
        panel.show(image)
        print("test pattern sent")

    time.sleep(0.2)
    panel.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
