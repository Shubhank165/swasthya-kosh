"""Kiosk screen for the 2.8" panel: renders what the patient sees, in their own language.

Rendering is separated from the panel transport on purpose. The renderer is pure Pillow and can be
checked by writing a PNG, which is how it was developed before any panel was attached; the SPI
driver only has to push finished pixels.

Text shaping matters more than it looks: Devanagari conjuncts (क्ष, त्र) and Tamil/Kannada
ligatures come out wrong without HarfBuzz. Pillow reports raqm support at import and this refuses
to render Indic text without it rather than drawing something subtly incorrect on a clinical
screen.

    python3 -m medikiosk.edge.display --demo out/          # render sample screens as PNGs
    python3 -m medikiosk.edge.display --question ask_fever --language ta --png screen.png
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from medikiosk.clinical.translations import PROMPT_TEXT, QUESTION_TEXT, prompt
from medikiosk.languages import LANGUAGES

# Panel is 320x240 landscape. Everything is sized for a patient reading at arm's length on a
# 2.8 inch screen, which is why there is one question per screen and nothing else competing.
WIDTH, HEIGHT = 320, 240

INK = (245, 245, 245)
PAPER = (18, 22, 28)
ACCENT = (90, 170, 255)
ALERT = (200, 40, 40)
MUTED = (140, 148, 160)


@dataclass(frozen=True)
class Screen:
    language: str
    headline: str
    hint: str = ""
    progress: tuple[int, int] | None = None
    alert: bool = False
    # Touch choices for the workflow stages that are not spoken questions - language, who is
    # answering, the Dashavidha options. Drawn as a numbered list so the same render works on the
    # 2.8 inch panel (where nothing is tappable) and on a tablet (where they are buttons).
    options: tuple[str, ...] = ()


# A language-picker screen shows every language in its own script, so one font cannot draw the
# list: Lohit-Devanagari has no Bengali or Tamil glyphs and renders them as tofu boxes. Pick the
# font from the script the text is actually written in rather than from the screen's language.
SCRIPT_RANGES: tuple[tuple[int, int, str], ...] = (
    (0x0900, 0x097F, "hi"),  # Devanagari - Hindi, Marathi
    (0x0980, 0x09FF, "bn"),
    (0x0A00, 0x0A7F, "pa"),  # Gurmukhi
    (0x0A80, 0x0AFF, "gu"),
    (0x0B80, 0x0BFF, "ta"),
    (0x0C00, 0x0C7F, "te"),
    (0x0C80, 0x0CFF, "kn"),
)


def script_of(text: str, default: str = "en") -> str:
    """The language whose font can draw this string, from the first Indic character in it."""

    for character in text:
        code = ord(character)
        for start, end, language in SCRIPT_RANGES:
            if start <= code <= end:
                return language
    return default


def font_for(language: str, size: int):
    """The installed font that actually covers this script."""

    from PIL import ImageFont

    try:
        path = subprocess.run(
            ["fc-match", "-f", "%{file}", f":lang={language}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        path = ""
    if not path or not Path(path).exists():
        path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(path, size)


def wrap(draw, text: str, font, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render(screen: Screen, scale: int = 1):
    """Draw a screen. PIL is imported here so a headless intake never needs an imaging library.

    `scale` multiplies the whole 320x240 layout. The SPI panel wants 1; a tablet standing in for
    the panel wants 4 or more, because upscaling a 320x240 render to a 10 inch screen turns crisp
    Devanagari conjuncts into mush. Everything is drawn at the scaled size rather than rendered
    small and enlarged, so the text stays sharp at any size.
    """

    from PIL import Image, ImageDraw, features

    if screen.language != "en" and not features.check("raqm"):
        raise RuntimeError(
            "Pillow has no raqm support, so Indic conjuncts would render incorrectly. "
            "Install libraqm before showing this screen to a patient."
        )

    width, height = WIDTH * scale, HEIGHT * scale
    image = Image.new("RGB", (width, height), PAPER)
    draw = ImageDraw.Draw(image)
    label = LANGUAGES[screen.language].native_name

    # Header strip: which language we are speaking, and how far along we are.
    draw.rectangle([0, 0, width, 30 * scale], fill=ALERT if screen.alert else (28, 34, 42))
    draw.text((10 * scale, 8 * scale), label, font=font_for(screen.language, 16 * scale), fill=INK)
    if screen.progress:
        done, total = screen.progress
        text = f"{done}/{total}"
        header_font = font_for("en", 14 * scale)
        draw.text(
            (width - 10 * scale - draw.textlength(text, font=header_font), 9 * scale),
            text,
            font=header_font,
            fill=INK if screen.alert else MUTED,
        )

    # The question, as large as it can be while still fitting: a patient reads this at arm's
    # length, and a scrollbar or an ellipsis on a clinical question is not acceptable.
    body_top = 44 * scale
    body_bottom = height - (34 if screen.hint else 12) * scale
    # Options need room of their own, so the headline only gets what is left over. The block is
    # capped at two thirds of the body and divided among however many options there are: nine
    # languages at full row height overflowed the screen and drew the list on top of the headline.
    options_block = 0
    option_height = 0
    if screen.options:
        options_block = int((body_bottom - body_top) * 0.66)
        option_height = options_block // len(screen.options)
    headline_bottom = body_bottom - options_block
    for size in (26, 24, 22, 20, 18, 16, 14):
        font = font_for(screen.language, size * scale)
        lines = wrap(draw, screen.headline, font, width - 24 * scale)
        line_height = int(size * scale * 1.45)
        if len(lines) * line_height <= headline_bottom - body_top:
            break
    y = body_top + max(0, (headline_bottom - body_top - len(lines) * line_height) // 2)
    for line in lines:
        draw.text((12 * scale, y), line, font=font, fill=INK)
        y += line_height

    if screen.options:
        # Text is sized to the row it has to fit in, not a fixed size, so a nine-item list stays
        # inside its boxes instead of spilling over the one below.
        option_size = max(9, min(20, int(option_height / (1.9 * scale)))) * scale
        gap = max(2, option_height // 10)
        y = headline_bottom
        for index, option in enumerate(screen.options, start=1):
            box = [12 * scale, y, width - 12 * scale, y + option_height - gap]
            draw.rectangle(box, outline=ACCENT, width=max(1, scale // 2))
            # Each option gets the font for its own script; the language list is written in seven
            # different ones and a single font renders most of them as empty boxes.
            option_font = font_for(script_of(option, screen.language), option_size)
            middle = y + (option_height - gap) // 2
            # The number is drawn with the Latin font, not the option's: padmaa (Gujarati) has no
            # digit glyphs, so "3." came out as a tofu box next to perfectly good Gujarati text.
            number_font = font_for("en", option_size)
            draw.text((24 * scale, middle), f"{index}.", font=number_font, fill=MUTED, anchor="lm")
            # anchor="lm" centres on the glyph box rather than the ascender, which is what kept
            # Tamil and Telugu rows sitting below their own outline.
            draw.text((72 * scale, middle), option, font=option_font, fill=INK, anchor="lm")
            y += option_height

    if screen.hint:
        hint_font = font_for(screen.language, 15 * scale)
        draw.line(
            [(12 * scale, height - 32 * scale), (width - 12 * scale, height - 32 * scale)],
            fill=(45, 52, 62),
        )
        draw.text((12 * scale, height - 26 * scale), screen.hint, font=hint_font, fill=ACCENT)
    return image


def question_screen(question_id: str, language: str, step: tuple[int, int] | None = None) -> Screen:
    # The hint must be in the same script as the body: falling back to English text drawn with an
    # Indic font produced a row of tofu boxes on the Tamil screen.
    return Screen(
        language=language,
        headline=QUESTION_TEXT[question_id][language],
        hint=prompt("speak_hint", language),
        progress=step,
    )


def prompt_screen(key: str, language: str, alert: bool = False) -> Screen:
    """A spoken prompt shown as it is spoken - greeting, retry, closing."""

    return Screen(language=language, headline=prompt(key, language), alert=alert)


def alert_screen(language: str) -> Screen:
    return Screen(language=language, headline=PROMPT_TEXT["emergency"][language], alert=True)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default="ask_complaint", choices=sorted(QUESTION_TEXT))
    parser.add_argument("--language", default="hi", choices=sorted(LANGUAGES))
    parser.add_argument("--png", type=Path, default=None)
    parser.add_argument("--demo", type=Path, default=None, help="render a sample set into a dir")
    args = parser.parse_args(argv)

    if args.demo:
        args.demo.mkdir(parents=True, exist_ok=True)
        written = []
        for language in sorted(LANGUAGES):
            image = render(question_screen("ask_complaint", language, step=(1, 7)))
            path = args.demo / f"screen_{language}.png"
            image.save(path)
            written.append(path.name)
        render(question_screen("ask_severity", "hi", step=(3, 7))).save(args.demo / "screen_hi_severity.png")
        render(alert_screen("hi")).save(args.demo / "screen_hi_alert.png")
        written += ["screen_hi_severity.png", "screen_hi_alert.png"]
        print(f"wrote {len(written)} screens to {args.demo}")
        return 0

    image = render(question_screen(args.question, args.language, step=(1, 7)))
    target = args.png or Path("screen.png")
    image.save(target)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
