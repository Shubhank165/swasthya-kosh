"""Numbers, and the units stuck to them — §18.

    102        102 F       102°F      39 C      about 102     around 100
    five       ५ (Devanagari)         twice a day

**Nothing is converted.** 102 °F is recorded as 102 with unit `fahrenheit`, not
as 38.9. The reason is the same one `Duration` gives for not normalising "about
two weeks" into seconds: a converted figure is a number the patient never said,
and 38.9 carries a precision that "about 102" did not have. The unit travels
with the value and the case summary prints both.

The one thing that *is* inferred is which unit an unmarked number is in, and
only where the ranges do not overlap: nobody has a temperature of 39 °F or 102
°C. That inference is marked `PROBABLE` rather than `CERTAIN`, because it is an
inference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from questioning_agent.core.enums import Certainty, Provenance
from questioning_agent.core.schemas import ParsedFact
from questioning_agent.interpretation.tokens import whole_word
from questioning_agent.localization.languages import Vocabulary

#: Digits in every script the app supports. Python's `int()` handles these
#: natively, but the regular expression has to be told they are digits.
_DIGITS = r"[0-9०-९০-৯੦-੯૦-૯௦-௯౦-౯೦-೯]"
_NUMBER = re.compile(rf"{_DIGITS}+(?:[.,]{_DIGITS}+)?")

_FAHRENHEIT = re.compile(r"°?\s*f\b|fahrenheit|फ़ारेनहाइट|फारेनहाइट", re.IGNORECASE)
_CELSIUS = re.compile(r"°?\s*c\b|celsius|centigrade|सेल्सियस", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Number:
    value: float
    unit: str | None
    approximate: bool
    evidence: str


def find_number(text: str, vocabulary: Vocabulary) -> Number | None:
    """The first number in `text`, as digits or as a word."""
    lowered = text.strip().lower()
    if not lowered:
        return None

    approximate = any(hedge in lowered for hedge in vocabulary.approximate)

    match = _NUMBER.search(lowered)
    if match:
        raw = match.group(0).replace(",", ".")
        try:
            value = float(_ascii_digits(raw))
        except ValueError:
            return None
        return Number(
            value=value,
            unit=None,
            approximate=approximate,
            evidence=match.group(0),
        )

    # Number words. Longest first, so "twenty five" is not read as "five".
    for word in sorted(vocabulary.numbers, key=len, reverse=True):
        if whole_word(word).search(lowered):
            return Number(
                value=vocabulary.numbers[word],
                unit=None,
                approximate=approximate,
                evidence=word,
            )
    return None


def parse_numeric(
    text: str,
    slot: str,
    vocabulary: Vocabulary,
    *,
    unit: str | None = None,
    units: tuple[str, ...] = (),
    minimum: float | None = None,
    maximum: float | None = None,
) -> ParsedFact:
    """A number for a numeric slot, with its unit where the question has one."""
    found = find_number(text, vocabulary)
    if found is None:
        return _uncertain(slot, text)

    chosen, inferred = _unit_for(text, found.value, unit, units)

    # Out of range is not an answer. A temperature of 9 is a typo or a
    # misunderstanding, and recording it would put a number in a case that a
    # practitioner has to disbelieve on sight.
    if minimum is not None and found.value < minimum:
        return _uncertain(slot, text)
    if maximum is not None and found.value > maximum:
        return _uncertain(slot, text)

    return ParsedFact(
        slot=slot,
        value={"value": found.value, "unit": chosen} if chosen else found.value,
        certainty=(
            Certainty.PROBABLE if (found.approximate or inferred) else Certainty.CERTAIN
        ),
        provenance=Provenance.SYSTEM_NORMALISED,
        evidence=found.evidence,
    )


def _unit_for(
    text: str, value: float, default: str | None, units: tuple[str, ...]
) -> tuple[str | None, bool]:
    """Which unit the patient meant, and whether that was inferred.

    Returns `(unit, inferred)`. Inferred units are marked probable upstream.
    """
    if not units:
        return default, False

    if "fahrenheit" in units or "celsius" in units:
        if _FAHRENHEIT.search(text):
            return "fahrenheit", False
        if _CELSIUS.search(text):
            return "celsius", False
        # Unmarked. The ranges do not overlap anywhere a person is alive, so
        # this is safe — and it is still an inference, so it is marked as one.
        if value >= 90:
            return "fahrenheit", True
        if value <= 45:
            return "celsius", True
        return default, True

    lowered = text.lower()
    for candidate in units:
        if candidate.lower() in lowered:
            return candidate, False
    return default, False


def _ascii_digits(raw: str) -> str:
    """Devanagari, Bengali, Tamil and the rest, as ASCII digits.

    Only the digits change. This is transliteration of a numeral system, not
    translation, and it is exact.
    """
    out = []
    for char in raw:
        if char.isdigit():
            out.append(str(int(char)))
        else:
            out.append(char)
    return "".join(out)


def _uncertain(slot: str, raw: str) -> ParsedFact:
    return ParsedFact(
        slot=slot,
        value=None,
        certainty=Certainty.UNCERTAIN,
        provenance=Provenance.SYSTEM_NORMALISED,
        evidence=raw.strip() or None,
    )


__all__ = ["Number", "find_number", "parse_numeric"]
