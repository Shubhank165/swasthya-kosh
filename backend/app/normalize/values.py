"""Coercion of kiosk field values into typed canonical values.

Pure. No clock, no I/O, no model.

The rule governing every function here is hard rule 2: **never silently increase
certainty**. Coercion may only lose ambiguity that was never there. Concretely:

- an unparseable value becomes `Text` carrying exactly what arrived, never a
  guess and never `None` — dropping it would be a silent loss;
- a value that arrives with a hedge (`"maybe"`, `"about"`, `"लगभग"`) marks the
  fact APPROXIMATE, and the hedge stays in `original_text`;
- `None` is never coerced into `false`. A field with no value is a field with no
  value, and its status already says why.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from app.domain.clinical.enums import Certainty
from app.domain.record import (
    Boolean,
    Coded,
    DateValue,
    Duration,
    FactValue,
    Quantity,
    Scale,
    Text,
)

#: Singular unit -> the canonical duration unit. The kiosk is inconsistent about
#: plurals and about Hindi unit words, and both spellings mean the same span.
_DURATION_UNITS: Mapping[str, str] = {
    "h": "hour",
    "hr": "hour",
    "hrs": "hour",
    "hour": "hour",
    "hours": "hour",
    "घंटा": "hour",
    "घंटे": "hour",
    "d": "day",
    "day": "day",
    "days": "day",
    "दिन": "day",
    "w": "week",
    "wk": "week",
    "week": "week",
    "weeks": "week",
    "हफ्ता": "week",
    "हफ्ते": "week",
    "सप्ताह": "week",
    "m": "month",
    "mo": "month",
    "month": "month",
    "months": "month",
    "महीना": "month",
    "महीने": "month",
    "y": "year",
    "yr": "year",
    "year": "year",
    "years": "year",
    "साल": "year",
    "वर्ष": "year",
}

#: Hedges, in the languages the kiosk is proven in. Their presence marks the
#: fact APPROXIMATE — which is the whole reason "maybe two weeks" cannot become
#: "2 weeks".
_HEDGES: tuple[str, ...] = (
    "maybe",
    "about",
    "around",
    "roughly",
    "approx",
    "approximately",
    "or so",
    "some",
    "शायद",
    "लगभग",
    "करीब",
    "तकरीबन",
    "आसपास",
)

_TRUE_TOKENS: frozenset[str] = frozenset(
    {"true", "yes", "y", "present", "haan", "haa", "हाँ", "हां", "जी", "जी हाँ"}
)
_FALSE_TOKENS: frozenset[str] = frozenset(
    {"false", "no", "n", "absent", "nahi", "nahin", "नहीं", "ना", "नही"}
)

#: `{"n": 3, "unit": "day"}` — the shape the Jetson's duration extractor emits.
_MAGNITUDE_KEYS: tuple[str, ...] = ("n", "magnitude", "value", "amount")

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
#: Devanagari digits. The extractor sometimes passes them through unconverted.
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def has_hedge(text: str | None) -> bool:
    """True when the patient hedged. Case-insensitive, script-aware."""
    if not text:
        return False
    lowered = text.lower()
    return any(hedge in lowered for hedge in _HEDGES)


def certainty_for(original_text: str | None, confidence: float | None) -> Certainty:
    """The strongest certainty this value is entitled to.

    A hedge caps it at APPROXIMATE regardless of how confident the ASR was: the
    machine's confidence in hearing "maybe" correctly says nothing about the
    patient's confidence in the answer.
    """
    if has_hedge(original_text):
        return Certainty.APPROXIMATE
    if confidence is not None and confidence < 0.6:
        return Certainty.UNCERTAIN
    return Certainty.REPORTED


def _normalise_digits(text: str) -> str:
    return text.translate(_DEVANAGARI_DIGITS)


def _first_number(text: str) -> float | None:
    match = _NUMBER.search(_normalise_digits(text))
    return None if match is None else float(match.group())


def _duration_unit(raw: str) -> str | None:
    return _DURATION_UNITS.get(raw.strip().lower())


def _coerce_mapping(raw: Mapping[str, Any], *, unit_hint: str | None) -> FactValue:
    """A structured value: `{"n": 3, "unit": "day"}`, `{"code": ...}`, `{"value": ...}`."""
    if "code" in raw:
        return Coded(
            code=str(raw["code"]),
            system=str(raw["system"]) if raw.get("system") else None,
            display=str(raw["display"]) if raw.get("display") else None,
        )

    magnitude: float | None = None
    for key in _MAGNITUDE_KEYS:
        candidate = raw.get(key)
        if isinstance(candidate, int | float) and not isinstance(candidate, bool):
            magnitude = float(candidate)
            break
        if isinstance(candidate, str):
            magnitude = _first_number(candidate)
            if magnitude is not None:
                break

    unit_raw = raw.get("unit") or unit_hint
    if magnitude is not None and unit_raw is not None:
        unit = _duration_unit(str(unit_raw))
        if unit is not None:
            return Duration(magnitude=magnitude, unit=unit)
        return Quantity(magnitude=magnitude, unit=str(unit_raw))

    if magnitude is not None and "max" in raw:
        maximum = raw["max"]
        if isinstance(maximum, int | float):
            return Scale(
                value=magnitude, minimum=float(raw.get("min", 0.0)), maximum=float(maximum)
            )

    # Understood as a mapping but not as any typed value. Preserved verbatim
    # rather than dropped: an unrecognised shape is still what the patient said.
    return Text(text=_render_mapping(raw))


def _render_mapping(raw: Mapping[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(raw.items()) if v is not None)


def _coerce_string(raw: str, *, unit_hint: str | None) -> FactValue:
    stripped = raw.strip()
    lowered = stripped.lower()

    if lowered in _TRUE_TOKENS:
        return Boolean(value=True)
    if lowered in _FALSE_TOKENS:
        return Boolean(value=False)

    if _looks_like_iso_date(stripped):
        # Checked before the numeric branch: `2026-08-14` starts with a number
        # and would otherwise become 2026 with a unit of "-08-14".
        return DateValue(value=date.fromisoformat(stripped))

    if _looks_like_code(stripped):
        # A snake_case token is the extractor's own vocabulary — `abdominal_pain`,
        # `type_2_diabetes` — not something a patient said. Coding it keeps the
        # report label separate from the machine-readable value.
        return Coded(code=stripped)

    match = _NUMBER.search(_normalise_digits(stripped))
    if match is not None:
        number = float(match.group())
        normalised = _normalise_digits(stripped)
        prefix = normalised[: match.start()].strip()
        suffix = normalised[match.end() :].strip()

        # A unit follows its magnitude. Text *before* the number means this is a
        # name carrying a strength — "Metformin 500", "Shelcal 500" — and
        # reading the name as a unit produces "500 Metformin", which is how a
        # dose ends up in a report meaning nothing at all.
        if prefix:
            return Text(text=stripped)

        unit_token = _unit_token(suffix) or (unit_hint or "")
        duration_unit = _duration_unit(unit_token)
        if duration_unit is not None:
            return Duration(magnitude=number, unit=duration_unit)
        if unit_token and len(unit_token) <= 16:
            return Quantity(magnitude=number, unit=unit_token)
        if not unit_token:
            # A bare number with no unit anywhere. `Quantity` refuses a unitless
            # magnitude on purpose, so this stays text: a bare 120 is not
            # clinical data and must not be dressed up as though it were.
            return Text(text=stripped)

    return Text(text=stripped)


def _unit_token(suffix: str) -> str:
    """The unit out of the text following a magnitude.

    "3 दिन से" is three days; the trailing postposition is grammar, not unit. So
    the whole suffix is tried first, then its leading token.
    """
    candidate = suffix.strip()
    if not candidate:
        return ""
    if _duration_unit(candidate) is not None:
        return candidate
    first = candidate.split()[0].strip(".,;:")
    return first if _duration_unit(first) is not None else candidate


#: A token in the extractor's own vocabulary: lowercase ASCII, underscores,
#: digits, no spaces. `abdominal_pain` is one; `Metformin 500` is not, and
#: neither is anything a patient actually said out loud.
_CODE_LIKE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")


def _looks_like_code(text: str) -> bool:
    return bool(_CODE_LIKE.match(text))


def _looks_like_iso_date(text: str) -> bool:
    if len(text) != 10:
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def coerce(raw: Any, *, unit_hint: str | None = None) -> FactValue | None:
    """The typed canonical value for a kiosk field value.

    `None` in gives `None` out — always. A missing value is not `false`, is not
    zero and is not an empty string, and this is the function where those
    collapses would happen if they were going to.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return Boolean(value=raw)
    if isinstance(raw, int | float):
        if unit_hint:
            duration_unit = _duration_unit(unit_hint)
            if duration_unit is not None:
                return Duration(magnitude=float(raw), unit=duration_unit)
            return Quantity(magnitude=float(raw), unit=unit_hint)
        return Scale(value=float(raw), minimum=0.0, maximum=10.0) if 0 <= raw <= 10 else Text(
            text=str(raw)
        )
    if isinstance(raw, str):
        return None if not raw.strip() else _coerce_string(raw, unit_hint=unit_hint)
    if isinstance(raw, Mapping):
        return _coerce_mapping(raw, unit_hint=unit_hint)
    if isinstance(raw, list | tuple):
        rendered = ", ".join(str(item) for item in raw if item is not None)
        return Text(text=rendered) if rendered else None
    if isinstance(raw, datetime):
        return DateValue(value=raw.date())
    if isinstance(raw, date):
        return DateValue(value=raw)
    return Text(text=str(raw))
