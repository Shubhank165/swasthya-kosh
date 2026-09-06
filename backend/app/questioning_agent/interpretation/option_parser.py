"""Reading a code out of what the patient wrote — §13, §14.

The patient is offered options and may still type a sentence. "It's a burning
pain" has to reach `pain.character = burning`, and it has to do it without a
model: exact match first, then the option's own label in that language, then the
synonym table.

**Negation applies here too.** "Not burning, more of a dull ache" must not match
`burning` merely because the word is present — the same failure as the fever
keyword, one layer down.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.questioning_agent.core.enums import Certainty, Provenance
from app.questioning_agent.core.schemas import ParsedFact
from app.questioning_agent.interpretation.negation import is_negated
from app.questioning_agent.interpretation.tokens import whole_word
from app.questioning_agent.localization.languages import Vocabulary


def match_options(
    text: str,
    options: tuple[str, ...],
    vocabulary: Vocabulary,
    labels: Mapping[str, str] | None = None,
) -> tuple[tuple[str, str], ...]:
    """Every option `text` names, as `(option_id, evidence)` pairs.

    Ordered by where they appear in the text, so a multi-select answer comes
    back in the order the patient said it — which is the order they will read it
    back in on the review screen.
    """
    lowered = text.strip().lower()
    if not lowered:
        return ()

    found: list[tuple[int, str, str]] = []
    for option in options:
        best = _first_match(lowered, option, vocabulary, labels)
        if best is None:
            continue
        position, evidence, span = best
        if is_negated(lowered, span, vocabulary.negation):
            continue
        found.append((position, option, evidence))

    found.sort()
    return tuple((option, evidence) for _, option, evidence in found)


def parse_single_select(
    text: str,
    slot: str,
    options: tuple[str, ...],
    vocabulary: Vocabulary,
    labels: Mapping[str, str] | None = None,
) -> ParsedFact:
    """One code, or nothing.

    Two matches is not one answer. "Sometimes burning, sometimes cramping" is a
    patient saying something the single-select cannot hold, and picking the
    first would discard the half of the sentence they thought was important.
    """
    matches = match_options(text, options, vocabulary, labels)
    if len(matches) != 1:
        return ParsedFact(
            slot=slot,
            value=None,
            certainty=Certainty.UNCERTAIN,
            provenance=Provenance.SYSTEM_NORMALISED,
            evidence=text.strip() or None,
        )
    option, evidence = matches[0]
    return ParsedFact(
        slot=slot,
        value=option,
        certainty=Certainty.CERTAIN,
        provenance=(
            Provenance.PATIENT_REPORTED
            if text.strip().lower() == option
            else Provenance.SYSTEM_NORMALISED
        ),
        evidence=evidence,
    )


def parse_multi_select(
    text: str,
    slot: str,
    options: tuple[str, ...],
    vocabulary: Vocabulary,
    labels: Mapping[str, str] | None = None,
) -> ParsedFact:
    """Every code the answer names."""
    matches = match_options(text, options, vocabulary, labels)
    if not matches:
        return ParsedFact(
            slot=slot,
            value=None,
            certainty=Certainty.UNCERTAIN,
            provenance=Provenance.SYSTEM_NORMALISED,
            evidence=text.strip() or None,
        )
    return ParsedFact(
        slot=slot,
        value=[option for option, _ in matches],
        certainty=Certainty.CERTAIN,
        provenance=Provenance.SYSTEM_NORMALISED,
        evidence=", ".join(evidence for _, evidence in matches),
    )


def _first_match(
    text: str,
    option: str,
    vocabulary: Vocabulary,
    labels: Mapping[str, str] | None = None,
) -> tuple[int, str, tuple[int, int]] | None:
    """Where `option` first appears, by any of its names.

    Four sources, and the label is the important one: it is the wording the
    patient was *shown*, so somebody who types back what they just read is
    understood without anybody having to have predicted that they would. It
    also means every option in all nine languages is matchable by its own
    words, without duplicating 194 labels into nine vocabularies.
    """
    names = {option, option.replace("_", " ")} | set(vocabulary.synonyms_for(option))
    if labels and (label := labels.get(option)):
        names.add(label.lower())

    best: tuple[int, str, tuple[int, int]] | None = None
    for name in names:
        if not name:
            continue
        match = whole_word(name).search(text)
        if match is None:
            continue
        if best is None or match.start() < best[0]:
            best = (match.start(), name, match.span())
    return best


__all__ = ["match_options", "parse_multi_select", "parse_single_select"]
