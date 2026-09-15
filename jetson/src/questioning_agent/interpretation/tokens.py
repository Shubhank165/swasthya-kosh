"""Word boundaries that work in nine scripts.

**`\\w` does not match an Indic vowel sign, and this is not a detail.**

In Devanagari, `बुखार` is `ब` + `ु` + `ख` + `ा` + `र`. The two vowel signs are
Unicode category `Mn` — combining marks — and Python's `re` counts them as
non-word characters. So `re.findall(r"\\w+", "बुखार")` returns
`['ब', 'ख', 'र']`: three fragments, none of which is the word.

The consequence was total. The Hindi vocabulary lists `बुखार`, and no token ever
equalled it, so:

- no yes/no answer in Hindi was ever recognised;
- `नहीं` never matched a negation cue, so no denial was ever detected;
- and every affected answer fell through to "uncertain", which at least failed
  safe — but a Hindi speaker could not answer a single question.

The same holds for Bengali, Gurmukhi, Gujarati, Tamil, Telugu and Kannada. Seven
of the nine languages, silently, and the English tests all passed.

The fix is a character class that includes the Indic blocks whole. They contain
letters, marks and digits, and all three belong inside a token.
"""

from __future__ import annotations

import re

#: Devanagari (0900) through Malayalam (0D7F), plus Sinhala's start. Covers
#: every script this project speaks, marks included.
_INDIC = "ऀ-෿"

#: One token: letters, digits, underscores, and Indic characters of any class.
WORD = rf"[\w{_INDIC}]"

_TOKEN = re.compile(rf"{WORD}+", re.UNICODE)


def words(text: str) -> list[str]:
    """`text` split into words, correctly, in any of the nine scripts."""
    return _TOKEN.findall(text)


def whole_word(term: str) -> re.Pattern[str]:
    """A pattern matching `term` only as a whole word.

    `\\b` has the same blind spot as `\\w` — it fires between a consonant and its
    own vowel sign — so this uses explicit lookarounds over the corrected class
    instead. Without it, searching for `हाँ` inside `हाँफना` would match.
    """
    return re.compile(rf"(?<!{WORD}){re.escape(term)}(?!{WORD})", re.UNICODE)


def contains_word(text: str, term: str) -> bool:
    return whole_word(term).search(text) is not None


__all__ = ["WORD", "contains_word", "whole_word", "words"]
