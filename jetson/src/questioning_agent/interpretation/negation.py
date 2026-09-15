"""Negation — §16.

**Searching for the symptom keyword is the bug this module exists to prevent.**
"I don't have fever" contains the word "fever". So does "no fever". So does
"the fever went away last week". A parser that looks for the word and stops
records the opposite of what the patient said, and it records it as a clinical
fact with the patient's name on it.

The approach is a scope, not a flag: a negation cue negates the words *after*
it, up to the next boundary. "No fever but I have a cough" negates the fever and
leaves the cough alone, because `but` ends the scope. That is the whole trick,
and it is enough for the sentences patients actually write.

Language-specific, because it has to be. Hindi puts its negation before the verb
at the end of the clause and English puts it before the noun; one regular
expression cannot do both, and pretending otherwise is how a Hindi speaker's
denial becomes an affirmation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from questioning_agent.interpretation.tokens import words


@dataclass(frozen=True, slots=True)
class NegationRules:
    """One language's negation cues and scope boundaries."""

    #: Words that start a negation.
    cues: frozenset[str]
    #: Words that end one. "No fever **but** a bad cough" — the cough is not
    #: negated, and without boundaries it would be.
    boundaries: frozenset[str]
    #: Cues that negate the whole sentence wherever they appear, because the
    #: language puts them at the end. Hindi's `नहीं` is the reason this exists.
    sentence_final: bool = False


def is_negated(text: str, span: tuple[int, int], rules: NegationRules) -> bool:
    """Whether the match at `span` falls inside a negation.

    `span` is a character range into `text` — the place the symptom word was
    found. Everything before it is scanned back to the nearest boundary, and if
    a cue turns up on the way, the match is negated.
    """
    before = text[: span[0]].lower()
    tokens = _tokens(before)

    for token in reversed(tokens):
        if token == _BOUNDARY_MARK or token in rules.boundaries:
            # A boundary closes any scope opened before it.
            break
        if token in rules.cues:
            return True

    if rules.sentence_final:
        # Languages that negate at the end of the clause. Scan forward to the
        # next boundary instead, which is the same rule with the direction
        # reversed rather than a separate mechanism.
        after = text[span[1] :].lower()
        for token in _tokens(after):
            if token == _BOUNDARY_MARK or token in rules.boundaries:
                break
            if token in rules.cues:
                return True

    return False


#: Punctuation that ends a negation scope, in every script here.
#:
#: "Not burning, more of a dull ache" was read as denying both, because the
#: comma vanished with the rest of the punctuation and the scan back from "dull"
#: walked straight past it into "not". A comma is a boundary in the sentences
#: people actually write, and dropping it made the parser deny a symptom the
#: patient had just described.
_BOUNDARY_MARK = "|"


def _tokens(text: str) -> list[str]:
    # `words()` rather than `\w+`: see `tokens.py`. Splitting Devanagari on
    # `\w` turns बुखार into three fragments and no negation cue ever matches.
    # Punctuation becomes an explicit boundary token rather than disappearing.
    marked = re.sub(r"[,.;:!?—–]", f" {_BOUNDARY_MARK} ", text)
    out: list[str] = []
    for chunk in marked.split():
        if chunk == _BOUNDARY_MARK:
            out.append(_BOUNDARY_MARK)
        else:
            out.extend(words(chunk))
    return out


__all__ = ["NegationRules", "is_negated"]
