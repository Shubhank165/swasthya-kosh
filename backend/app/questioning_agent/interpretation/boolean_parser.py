"""Yes, no, and "I think maybe" — §13, §19.

Three outcomes, not two. The third is the one that matters: a patient who says
"I think maybe" has not said yes, and a parser that rounds them to one has put
a symptom in a clinical record on the strength of a hedge.
"""

from __future__ import annotations

from app.questioning_agent.core.enums import Certainty, Provenance
from app.questioning_agent.core.schemas import ParsedFact
from app.questioning_agent.interpretation.negation import is_negated
from app.questioning_agent.interpretation.tokens import whole_word, words
from app.questioning_agent.localization.languages import Vocabulary


def parse_boolean(text: str, slot: str, vocabulary: Vocabulary) -> ParsedFact:
    """Read a yes/no answer out of whatever the patient wrote."""
    lowered = text.strip().lower()
    if not lowered:
        return _uncertain(slot, text)

    tokens = words(lowered)
    token_set = set(tokens)

    hedged = bool(token_set & vocabulary.unsure)

    # A denial is checked before an affirmation, because "no, yes I mean"
    # is rare and "yes, but no fever" is not — and because a stray affirming
    # particle at the start of a sentence ("ok, I don't have it") is common
    # enough to matter.
    if token_set & vocabulary.deny:
        return _fact(slot, False, text, hedged, _first(tokens, vocabulary.deny))

    if token_set & vocabulary.affirm:
        matched = _first(tokens, vocabulary.affirm)
        # "Yes" inside a negation is still a no: "no, yes it hurts" is not the
        # sentence, but "I would not say yes" is.
        span = _span_of(lowered, matched)
        if span and is_negated(lowered, span, vocabulary.negation):
            return _fact(slot, False, text, hedged, matched)
        return _fact(slot, True, text, hedged, matched)

    return _uncertain(slot, text)


def _fact(
    slot: str, value: bool, raw: str, hedged: bool, evidence: str | None
) -> ParsedFact:
    return ParsedFact(
        slot=slot,
        value=value,
        # A hedge does not become an answer. "Maybe yes" is `PROBABLE`, which
        # the state files but the case summary marks — and which a later plain
        # answer is allowed to overwrite.
        certainty=Certainty.PROBABLE if hedged else Certainty.CERTAIN,
        provenance=Provenance.SYSTEM_NORMALISED,
        evidence=evidence or raw.strip() or None,
    )


def _uncertain(slot: str, raw: str) -> ParsedFact:
    """Nothing matched. Not a no — an unread answer."""
    return ParsedFact(
        slot=slot,
        value=None,
        certainty=Certainty.UNCERTAIN,
        provenance=Provenance.SYSTEM_NORMALISED,
        evidence=raw.strip() or None,
    )


def _first(tokens: list[str], vocabulary_words: frozenset[str]) -> str | None:
    for token in tokens:
        if token in vocabulary_words:
            return token
    return None


def _span_of(text: str, word: str | None) -> tuple[int, int] | None:
    if not word:
        return None
    match = whole_word(word).search(text)
    return match.span() if match else None


__all__ = ["parse_boolean"]
