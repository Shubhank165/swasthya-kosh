"""Turn OCR lines from a prescription into structured medications, diagnoses and lab values.

Deterministic patterns first, the local model only for lines the patterns do not recognise. That
order matters: Indian prescriptions are highly conventional - `Tab Augmentin 625 mg BD x 5 days`
follows a form a regex reads exactly, every time, in a millisecond. Handing that to a 1B model
would trade a correct answer for a plausible one.

Nothing here is trusted. Every extraction carries a confidence and reaches the doctor's sheet
marked as machine-derived, because OCR misreads dosages and a wrong dose is the most dangerous
thing this system can put in front of a clinician. A value that cannot be parsed is reported as
unparsed rather than guessed at.
"""

from __future__ import annotations

import re
from typing import Any

# Dose forms as they are actually written on Indian prescriptions.
FORM = r"(?:tab|tablet|cap|capsule|syp|syrup|inj|injection|oint|drops?|susp)"
# Frequencies: Latin abbreviations plus the numeric form (1-0-1 = morning, noon, night).
FREQUENCY = r"(?:OD|BD|TDS|TID|QID|HS|SOS|PRN|STAT|Q\d+H|\d\s*-\s*\d\s*-\s*\d)"
STRENGTH = r"\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|IU|units?)"
# Plurals first: regex alternation takes the first match, so "day|days" captures "5 day".
DURATION = r"(?:x|for)\s*\d+\s*(?:days?|weeks?|months?)"

MEDICATION = re.compile(
    rf"(?P<form>{FORM})?\.?\s*"
    rf"(?P<name>[A-Za-z][A-Za-z0-9\-]{{2,}}(?:\s+[A-Z][A-Za-z0-9\-]+)?)\s*"
    rf"(?P<strength>{STRENGTH})?\s*"
    rf"(?P<frequency>{FREQUENCY})?\s*"
    rf"(?P<duration>{DURATION})?",
    re.IGNORECASE,
)

DIAGNOSIS = re.compile(r"(?:diagnosis|impression|dx)\s*[:\-]\s*(?P<text>.+)", re.IGNORECASE)

# "Hemoglobin 10.2 g/dL (13-17)" and its many spacings.
LAB = re.compile(
    r"(?P<test>[A-Za-z][A-Za-z ()/\-]{2,30}?)\s*[:\-]?\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>%|g/dL|mg/dL|mmol/L|IU/L|U/L|cells/[a-zA-Z]+|/[a-zA-Z]+)"
    r"(?:\s*\(?(?P<low>\d+(?:\.\d+)?)\s*[-–]\s*(?P<high>\d+(?:\.\d+)?)\)?)?",
    re.IGNORECASE,
)

# Words that look like drug names to the pattern but are prescription furniture.
NOT_A_DRUG = {
    "diagnosis", "impression", "patient", "name", "age", "sex", "date", "doctor", "dr",
    "hospital", "clinic", "advice", "follow", "review", "signature", "regd", "reg",
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" .,:;-")


def _medication(line: str) -> dict[str, Any] | None:
    match = MEDICATION.search(line)
    if not match:
        return None
    name = _clean(match.group("name") or "")
    if not name or name.lower() in NOT_A_DRUG:
        return None

    strength = match.group("strength")
    frequency = match.group("frequency")
    # A bare word is not a prescription line. Requiring a strength or a frequency is what keeps
    # "Follow up after 5 days" from being recorded as a drug.
    if not strength and not frequency:
        return None

    # Confidence reflects how much of the expected shape was actually present, so a doctor can
    # see which lines were read whole and which were guessed at from a fragment.
    present = sum(bool(x) for x in (strength, frequency, match.group("duration")))
    return {
        "kind": "MEDICATION",
        "name": name,
        "form": (match.group("form") or "").lower() or None,
        "strength": _clean(strength) if strength else None,
        "frequency": (frequency or "").upper() or None,
        "duration": _clean(match.group("duration")) if match.group("duration") else None,
        "confidence": round(0.5 + 0.15 * present, 2),
        "line": line,
    }


def _diagnosis(line: str) -> dict[str, Any] | None:
    match = DIAGNOSIS.search(line)
    if not match:
        return None
    text = _clean(match.group("text"))
    if not text:
        return None
    # An explicit "Diagnosis:" label is a strong signal; the text after it is taken as written.
    return {"kind": "DIAGNOSIS", "text": text, "confidence": 0.8, "line": line}


def _lab(line: str) -> dict[str, Any] | None:
    match = LAB.search(line)
    if not match:
        return None
    test = _clean(match.group("test"))
    if not test or test.lower() in NOT_A_DRUG:
        return None
    value = float(match.group("value"))
    low, high = match.group("low"), match.group("high")

    flag = None
    if low and high:
        # Only flag against a range printed on the report itself. Built-in reference ranges vary
        # by lab and by population, and applying the wrong one is worse than applying none.
        flag = "low" if value < float(low) else "high" if value > float(high) else "normal"

    return {
        "kind": "LAB",
        "test": test,
        "value": value,
        "unit": match.group("unit"),
        "reference_low": float(low) if low else None,
        "reference_high": float(high) if high else None,
        "flag": flag,
        "confidence": 0.85 if flag else 0.7,
        "line": line,
    }


def extract(lines: list[str]) -> dict[str, Any]:
    """Structure a document's OCR lines. Unrecognised lines are reported, never invented."""

    found: list[dict[str, Any]] = []
    unparsed: list[str] = []

    for raw in lines:
        line = _clean(raw)
        if len(line) < 3:
            continue
        # Diagnosis and lab patterns are checked first: both are more specific than the
        # medication pattern, which would otherwise claim "Hemoglobin 10.2 g/dL" as a drug.
        item = _diagnosis(line) or _lab(line) or _medication(line)
        if item:
            found.append(item)
        else:
            unparsed.append(line)

    by_kind: dict[str, list[dict[str, Any]]] = {"MEDICATION": [], "DIAGNOSIS": [], "LAB": []}
    for item in found:
        by_kind[item["kind"]].append(item)

    return {
        "medications": by_kind["MEDICATION"],
        "diagnoses": by_kind["DIAGNOSIS"],
        "labs": by_kind["LAB"],
        "unparsed": unparsed,
        "parsed_count": len(found),
        "line_count": len([line for line in lines if len(_clean(line)) >= 3]),
        "disclaimer": (
            "Read from a photograph by OCR and parsed by pattern. Every value requires clinician "
            "confirmation against the original document, especially doses."
        ),
    }
