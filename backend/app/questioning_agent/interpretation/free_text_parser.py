"""Several facts out of one sentence — §13.

    "It's a burning pain on the right side of my stomach and gets worse
     after eating."

        pain.character   burning
        pain.site        upper_abdomen
        pain.aggravating eating

This is the part of the system that earns the "natural-language capable" claim,
and it is still nothing but dictionaries and regular expressions. Each target
slot is asked, in turn, whether it can find itself in the sentence — a code slot
looks for its own allowed values, a duration slot looks for a duration, a
boolean looks for a yes.

**A slot that finds nothing stays empty.** No slot is filled from a sentence
merely because the sentence was long, and nothing infers one slot from another:
`character = burning` does not suggest anything about the site.

The aggravating and relieving factors are the one place free text is kept as
text. "After eating" is not a code and forcing it into one would lose the
patient's own description, which is exactly what the practitioner wants to read.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from app.questioning_agent.core.enums import Certainty, DataType, Provenance
from app.questioning_agent.core.schemas import ParsedFact
from app.questioning_agent.interpretation.boolean_parser import parse_boolean
from app.questioning_agent.interpretation.duration_parser import find_duration
from app.questioning_agent.interpretation.numeric_parser import parse_numeric
from app.questioning_agent.interpretation.option_parser import match_options
from app.questioning_agent.knowledge.information_schema import SlotRegistry
from app.questioning_agent.localization.languages import Vocabulary

#: Clauses that introduce what makes something worse or better. Ordered longest
#: first so "gets worse after" beats "after".
_CUES: dict[str, tuple[str, ...]] = {
    "aggravating": (
        "gets worse after",
        "gets worse when",
        "worse after",
        "worse when",
        "worse on",
        "aggravated by",
        "brought on by",
        "triggered by",
        "से बढ़ता है",
        "के बाद बढ़ता",
    ),
    "relieving": (
        "gets better after",
        "gets better when",
        "better after",
        "better when",
        "relieved by",
        "settles with",
        "helps",
        "से आराम",
        "से ठीक",
    ),
}


def parse_free_text(
    text: str,
    targets: tuple[str, ...],
    slots: SlotRegistry,
    vocabulary: Vocabulary,
    labels: Mapping[str, str] | None = None,
) -> tuple[ParsedFact, ...]:
    """Everything the sentence yields, one fact per target it can fill."""
    raw = text.strip()
    if not raw:
        return ()

    # A question with one target is *about* that thing, so an untagged text slot
    # takes the whole answer. A question with several is not: "It's a burning
    # pain" would otherwise be filed as the answer to `pain.radiation` as well
    # as `pain.character`, because a bare text slot accepts anything. One of
    # those is what the patient said; the other is the engine putting words in
    # their mouth about where the pain travels.
    sole_target = len(targets) == 1

    facts: list[ParsedFact] = []
    for target in targets:
        slot = slots.get(target)
        if slot is None:
            continue
        fact = _for_slot(
            raw,
            target,
            slot.data_type,
            slot.allowed_values,
            vocabulary,
            sole_target=sole_target,
            labels=labels,
        )
        if fact is not None:
            facts.append(fact)
    return tuple(facts)


def _for_slot(
    text: str,
    target: str,
    data_type: DataType,
    allowed: tuple[str, ...],
    vocabulary: Vocabulary,
    *,
    sole_target: bool,
    labels: Mapping[str, str] | None = None,
) -> ParsedFact | None:
    local = target.split(".", 1)[-1]

    # The two text slots that keep the patient's own words rather than a code.
    if local in _CUES and data_type is DataType.TEXT:
        clause = _clause_after(text, _CUES[local])
        if clause:
            return ParsedFact(
                slot=target,
                value=clause,
                certainty=Certainty.PROBABLE,
                provenance=Provenance.SYSTEM_NORMALISED,
                evidence=clause,
            )
        return None

    if data_type in (DataType.CODE, DataType.CODE_SET):
        matches = match_options(text, allowed, vocabulary, labels)
        if not matches:
            return None
        if data_type is DataType.CODE_SET:
            return ParsedFact(
                slot=target,
                value=[option for option, _ in matches],
                certainty=Certainty.PROBABLE,
                provenance=Provenance.SYSTEM_NORMALISED,
                evidence=", ".join(e for _, e in matches),
            )
        if len(matches) != 1:
            return None
        option, evidence = matches[0]
        return ParsedFact(
            slot=target,
            value=option,
            certainty=Certainty.PROBABLE,
            provenance=Provenance.SYSTEM_NORMALISED,
            evidence=evidence,
        )

    if data_type is DataType.DURATION:
        duration = find_duration(text, vocabulary)
        if duration is None:
            return None
        return ParsedFact(
            slot=target,
            value=duration.model_dump(),
            certainty=Certainty.PROBABLE if duration.approximate else Certainty.CERTAIN,
            provenance=Provenance.SYSTEM_NORMALISED,
            evidence=text,
        )

    if data_type in (DataType.NUMBER, DataType.SCALE):
        fact = parse_numeric(text, target, vocabulary)
        return fact if fact.usable else None

    if data_type is DataType.BOOLEAN:
        fact = parse_boolean(text, target, vocabulary)
        return fact if fact.usable else None

    if data_type is DataType.TEXT:
        # Kept whole, but only when the question was about this one thing. See
        # `sole_target` above.
        if not sole_target:
            return None
        return ParsedFact(
            slot=target,
            value=text,
            certainty=Certainty.CERTAIN,
            provenance=Provenance.PATIENT_REPORTED,
            evidence=text,
        )

    return None


def _clause_after(text: str, cues: tuple[str, ...]) -> str | None:
    """What follows the first cue, to the end of the clause.

    Deliberately crude: everything up to the next connective or full stop. A
    grammar would be more precise and would also be a parser nobody can review
    when it puts the wrong half of a sentence in a clinical record.
    """
    lowered = text.lower()
    for cue in sorted(cues, key=len, reverse=True):
        index = lowered.find(cue)
        if index == -1:
            continue
        rest = text[index + len(cue) :].strip()
        clause = re.split(r"[.;,]|\band\b|\bbut\b|\bऔर\b|\bलेकिन\b", rest, maxsplit=1)[0]
        clause = clause.strip()
        if clause:
            return clause
    return None


__all__ = ["parse_free_text"]
