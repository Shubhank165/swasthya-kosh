"""The patient's slip as a PDF: token number, where to go, what was recorded.

Rendered with Pillow rather than a PDF library because Pillow is already on the Jetson with
libraqm, which is what makes Devanagari conjuncts and matras come out in the right order.
A PDF toolkit that lays out Latin text perfectly and Hindi wrongly is worse than no slip.

Paper is A5-ish at 150 dpi. A thermal or A4 printer will scale it; a phone will read it.
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, MARGIN = 874, 1240, 60  # A5 at 150 dpi
DEVANAGARI = re.compile(r"[ऀ-ॿ]")

# Ubuntu's default font packages on the Jetson image; both are checked before use.
DEFAULT_FONTS = {
    "deva": Path("/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf"),
    "latin": Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
}


def _font(path: Path | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if path is not None and Path(path).exists():
        return ImageFont.truetype(str(path), size)
    # No font on this machine (tests on Windows): the PDF still renders, Latin only.
    return ImageFont.load_default(size)


def render(report: dict, language: str, fonts: dict[str, Path | None] | None = None) -> bytes:
    """One page. Returns PDF bytes."""

    fonts = fonts or DEFAULT_FONTS
    hi = language == "hi"

    def local(en: str, hin: str) -> str:
        return hin if hi else en

    def pick(text: str, size: int):
        key = "deva" if DEVANAGARI.search(text) else "latin"
        return _font(fonts.get(key), size)

    page = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(page)
    y = MARGIN

    def line(text: str, size: int = 30, gap: int = 12, bold_rule: bool = False) -> None:
        nonlocal y
        for chunk in _wrap(text, 40 if size >= 30 else 56):
            draw.text((MARGIN, y), chunk, fill="black", font=pick(chunk, size))
            y += size + gap
        if bold_rule:
            draw.line((MARGIN, y, WIDTH - MARGIN, y), fill="black", width=3)
            y += 24

    queue = report.get("queue_entry") or {}
    routing = report.get("routing") or {}
    registration = report.get("registration") or {}
    clinical = report.get("clinical") or {}
    generated = report.get("generated_at") or datetime.now().isoformat()

    line(local("MediKiosk - OPD slip", "मेडीकियोस्क - ओपीडी पर्ची"), 40, 16, bold_rule=True)

    # The two things the patient actually needs, biggest on the page.
    number = queue.get("number")
    line(local("Token", "टोकन") + f"  {number if number is not None else '-'}", 96, 20)
    line(local("Queue", "कतार") + f": {queue.get('specialty') or routing.get('queue') or '-'}", 34)
    if queue.get("band"):
        line(local("Priority", "प्राथमिकता") + f": {queue['band']}", 28)
    line(local("Time", "समय") + f": {generated[:16].replace('T', ' ')}", 26, 24, bold_rule=True)

    name = registration.get("name")
    age = registration.get("age")
    parts = [p for p in (name, f"{age} {local('yrs', 'वर्ष')}" if age is not None else None) if p]
    if parts:
        line(local("Patient", "मरीज़") + ": " + ", ".join(str(p) for p in parts), 28)
    if clinical.get("complaint"):
        line(local("Complaint", "समस्या") + f": {clinical['complaint']}", 28)
    if clinical.get("duration"):
        line(local("Since", "कब से") + f": {clinical['duration']}", 28)
    if clinical.get("severity") is not None:
        line(local("Severity", "तीव्रता") + f": {clinical['severity']}/10", 28)
    flags = [f.get("message") or f.get("rule_id") for f in report.get("red_flags") or []]
    if flags:
        line(local("Urgent findings", "तत्काल संकेत") + ": " + "; ".join(map(str, flags)), 28)
    prakriti = report.get("prakriti") or {}
    if prakriti.get("prakriti"):
        line(
            local("Prakriti (provisional)", "प्रकृति (अस्थायी)")
            + f": {prakriti.get('prakriti_hi') if hi else prakriti['prakriti']}",
            28,
        )

    y += 12
    encounter = str(report.get("encounter_id") or "")[:8]
    hospital = report.get("hospital_intake_id")
    line(
        local("Record", "रिकॉर्ड")
        + f": {encounter}"
        + (f"  •  {local('sent to hospital', 'अस्पताल को भेजा')}" if hospital else ""),
        22,
        8,
    )
    line(
        local(
            "Patient-reported history only. Not a diagnosis. Staff will review it.",
            "केवल मरीज़ द्वारा बताया गया इतिहास। यह निदान नहीं है। कर्मचारी इसकी समीक्षा करेंगे।",
        ),
        22,
        8,
    )

    out = io.BytesIO()
    page.save(out, format="PDF", resolution=150)
    return out.getvalue()


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    return lines + [current] if current else lines or [""]
