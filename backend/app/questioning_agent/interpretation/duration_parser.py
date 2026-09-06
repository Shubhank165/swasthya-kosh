"""How long — §17.

    three days      about a week      since yesterday     2 weeks ago
    for the last 4-5 days             कल से              ஒரு வாரமாக

**Where the expression is genuinely vague, the vagueness is preserved.** "About
a week" becomes 7 days marked approximate, not 7 days; "four or five days"
becomes the lower bound marked approximate, not 4.5. A questionnaire that
sharpens a patient's hedge into a figure has invented precision, and the
practitioner reading the case has no way to know it was invented.

"Comes and goes" is not a duration at all. It is a *pattern*, and the free-text
parser picks it up as one; this module returns nothing for it rather than
guessing a length.
"""

from __future__ import annotations

import re

from app.questioning_agent.core.enums import Certainty, Provenance
from app.questioning_agent.core.schemas import Duration, ParsedFact
from app.questioning_agent.interpretation.numeric_parser import _DIGITS, find_number
from app.questioning_agent.interpretation.tokens import WORD
from app.questioning_agent.localization.languages import Vocabulary

#: "4-5 days", "four or five days". The lower bound wins and the result is
#: approximate — a range is a patient saying they do not know, and the honest
#: reading of "4 or 5" is "at least 4".
_RANGE = re.compile(rf"({_DIGITS}+)\s*(?:-|–|to|or|या|से)\s*({_DIGITS}+)", re.UNICODE)


def parse_duration(text: str, slot: str, vocabulary: Vocabulary) -> ParsedFact:
    """Read a length of time out of ordinary language."""
    duration = find_duration(text, vocabulary)
    if duration is None:
        return ParsedFact(
            slot=slot,
            value=None,
            certainty=Certainty.UNCERTAIN,
            provenance=Provenance.SYSTEM_NORMALISED,
            evidence=text.strip() or None,
        )
    return ParsedFact(
        slot=slot,
        value=duration.model_dump(),
        certainty=Certainty.PROBABLE if duration.approximate else Certainty.CERTAIN,
        provenance=Provenance.SYSTEM_NORMALISED,
        evidence=text.strip() or None,
    )


def find_duration(text: str, vocabulary: Vocabulary) -> Duration | None:
    """The duration in `text`, or `None` when there is not one."""
    lowered = text.strip().lower()
    if not lowered:
        return None

    # 1. Fixed expressions — "yesterday", "since last month". These carry their
    #    own unit and do not need a number beside them.
    hedged = any(hedge in lowered for hedge in vocabulary.approximate)
    for phrase in sorted(vocabulary.temporal, key=len, reverse=True):
        if phrase in lowered:
            value, phrase_unit = vocabulary.temporal[phrase]
            return Duration(
                value=value,
                unit=phrase_unit,
                # "Yesterday" is exact. "A few days" is not, and neither is
                # "about a week" — the hedge is in the sentence rather than in
                # the phrase, so both have to be looked at. Reading "about a
                # week" as exactly seven days is the invented precision this
                # module exists to avoid.
                approximate=hedged
                or phrase in vocabulary.approximate
                or value not in (0, 1),
            )

    found_unit = _unit_in(lowered, vocabulary)
    if found_unit is None:
        return None
    unit: str = found_unit

    # 2. A range. Checked before a single number, because "4-5 days" contains a
    #    single number twice and the first one alone would read as exact.
    ranged = _RANGE.search(lowered)
    if ranged:
        try:
            low = float(_ascii(ranged.group(1)))
        except ValueError:
            low = 0.0
        return Duration(value=low, unit=unit, approximate=True)

    # 3. A plain number with a unit beside it.
    number = find_number(lowered, vocabulary)
    if number is None:
        # "For a week" — no numeral, but a unit and an article. One is the only
        # reading, and it is the reading a person would give.
        return Duration(value=1, unit=unit, approximate=False)

    return Duration(
        value=number.value,
        unit=unit,
        approximate=number.approximate,
    )


def _unit_in(text: str, vocabulary: Vocabulary) -> str | None:
    """The duration unit named in `text`, longest match first."""
    best: tuple[int, str] | None = None
    for canonical, words in vocabulary.duration_units.items():
        for word in words:
            matched = re.search(rf"(?<!{WORD}){re.escape(word)}", text, flags=re.UNICODE)
            if matched and (best is None or len(word) > best[0]):
                best = (len(word), canonical)
    return best[1] if best else None


def _ascii(raw: str) -> str:
    return "".join(str(int(c)) if c.isdigit() else c for c in raw)


__all__ = ["find_duration", "parse_duration"]
