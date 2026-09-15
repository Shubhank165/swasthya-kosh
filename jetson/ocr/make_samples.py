"""Generate printed Devanagari/English test pages with ground truth.

These are *printed* samples. They exercise mixed-script reading - Hindi, Latin drug names, doses,
`1-0-1` schedules - and image degradation, which is most of what a lab report or a computer-printed
prescription needs. They say nothing about doctor handwriting: no generator can fake that, so real
photographed prescriptions have to be dropped into ocr/samples/ before any handwriting claim.

    python -m ocr.make_samples
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path("ocr/samples")

# Nirmala UI ships with Windows and covers Devanagari; the others are fallbacks.
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\Nirmala.ttc",
    r"C:\Windows\Fonts\Nirmala.ttf",
    r"C:\Windows\Fonts\mangal.ttf",
    "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    "/usr/share/fonts/truetype/Sarai/Sarai.ttf",
]

PAGES: dict[str, tuple[list[str], list[str]]] = {
    "prescription_printed": (
        [
            "आयुर्वेद चिकित्सालय, नई दिल्ली",
            "रोगी: राम कुमार        आयु: 45        दिनांक: 12/06/2026",
            "निदान: मधुमेह टाइप 2",
            "",
            "Rx",
            "1. Metformin 500 mg    1-0-1    खाने के बाद",
            "2. Pantoprazole 40 mg  1-0-0    खाली पेट",
            "3. त्रिफला चूर्ण 5 ग्राम   रात को    गर्म पानी के साथ",
            "",
            "जाँच: HbA1c, Fasting Blood Sugar",
            "अगली भेंट: 7 दिन बाद",
        ],
        ["Metformin", "500 mg", "1-0-1", "Pantoprazole", "40 mg", "HbA1c", "12/06/2026", "मधुमेह"],
    ),
    "lab_report_printed": (
        [
            "पैथोलॉजी रिपोर्ट / PATHOLOGY REPORT",
            "Patient: Sunita Devi        Age: 52 / F",
            "Collected: 12/06/2026",
            "",
            "Test                 Result      Unit      Reference",
            "Haemoglobin          11.0        g/dL      12.0 - 15.0",
            "HbA1c                8.2         %         4.0 - 5.6",
            "Fasting Glucose      148         mg/dL     70 - 100",
            "Creatinine           0.9         mg/dL     0.6 - 1.1",
            "",
            "टिप्पणी: हीमोग्लोबिन संदर्भ सीमा से कम है।",
        ],
        ["Haemoglobin", "11.0", "g/dL", "HbA1c", "8.2", "148", "mg/dL", "0.9"],
    ),
    "discharge_note_printed": (
        [
            "डिस्चार्ज सारांश",
            "रोगी: मोहन लाल      आयु: 61      भर्ती: 02/05/2026      छुट्टी: 06/05/2026",
            "",
            "निदान: तीव्र पेट दर्द, पित्ताशय की पथरी",
            "प्रक्रिया: Laparoscopic Cholecystectomy",
            "",
            "दवाइयाँ:",
            "Tab Amoxicillin 625 mg  1-1-1  5 दिन",
            "Tab Paracetamol 650 mg  SOS   बुखार या दर्द में",
            "",
            "सलाह: भारी वजन न उठाएँ। 10 दिन बाद जाँच।",
        ],
        ["Amoxicillin", "625 mg", "1-1-1", "Paracetamol", "650 mg", "Cholecystectomy"],
    ),
}


def pick_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise RuntimeError(f"No Devanagari font found. Tried: {FONT_CANDIDATES}")


def render(lines: list[str], width: int = 1240, size: int = 30) -> Image.Image:
    font = pick_font(size)
    height = 90 + len(lines) * int(size * 1.6)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    y = 45
    for line in lines:
        draw.text((55, y), line, font=font, fill=(15, 15, 15))
        y += int(size * 1.6)
    return image


def degrade(image: Image.Image, seed: int) -> Image.Image:
    """Photographed-on-a-phone conditions: slight rotation, blur, grey cast, JPEG-ish noise."""

    random.seed(seed)
    out = image.rotate(random.uniform(-1.6, 1.6), expand=True, fillcolor="white")
    out = out.filter(ImageFilter.GaussianBlur(radius=0.7))
    pixels = out.load()
    for _ in range(int(out.width * out.height * 0.012)):
        x = random.randrange(out.width)
        y = random.randrange(out.height)
        shade = random.randrange(90, 190)
        pixels[x, y] = (shade, shade, shade)
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for name, (lines, keywords) in PAGES.items():
        clean = render(lines)
        for variant, image in (("clean", clean), ("photo", degrade(clean, seed=len(name)))):
            stem = OUT / f"{name}_{variant}"
            image.save(stem.with_suffix(".png"))
            text = "\n".join(line for line in lines if line.strip())
            stem.with_suffix(".gt.txt").write_text(text, encoding="utf-8")
            stem.with_suffix(".keywords.txt").write_text("\n".join(keywords), encoding="utf-8")
            written.append(stem.name + ".png")
    print(f"wrote {len(written)} pages to {OUT}:")
    for name in written:
        print(f"  {name}")
    print(
        "\nThese are printed pages only. Photograph real prescriptions - especially handwritten "
        "ones - into the same folder with matching .gt.txt files before trusting any ranking."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
