"""Deterministic fuzzy matching for terminology search.

Trigram similarity over a normalised, transliterated form. No embeddings, no
model, no network — the same query returns the same ranked candidates on a
kiosk with no internet as it does in the cloud.

An embedding-based matcher is a later provider behind the same interface. It
will rank better; it will not be allowed to invent a mapping that does not
exist, which is the property this module has by construction.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

#: Devanagari -> Latin, for the transliterated forms patients and staff type.
#: Covers the vowels, consonants and matras needed for the terminology seeds;
#: it is a search aid, not a scholarly transliteration scheme.
_DEVANAGARI_MAP: dict[str, str] = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ii", "उ": "u", "ऊ": "uu",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "अं": "am",
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    "ं": "n", "ँ": "n", "ः": "h", "्": "", "़": "",  # noqa: RUF001
}

#: Latin spellings that vary between transliteration conventions. Folding these
#: is what makes "shula", "sula" and "shoola" all find the same concept.
_FOLDINGS: tuple[tuple[str, str], ...] = (
    ("aa", "a"),
    ("ee", "i"),
    ("ii", "i"),
    ("oo", "u"),
    ("uu", "u"),
    ("sh", "s"),
    ("ss", "s"),
    ("chh", "ch"),
    ("kh", "k"),
    ("gh", "g"),
    ("jh", "j"),
    ("th", "t"),
    ("dh", "d"),
    ("ph", "f"),
    ("bh", "b"),
    ("v", "w"),
    ("y", "i"),
)


def transliterate(text: str) -> str:
    """Devanagari to a Latin approximation, leaving Latin text untouched."""
    return "".join(_DEVANAGARI_MAP.get(ch, ch) for ch in text)


def fold(text: str) -> str:
    """Normalise a string to its comparison form.

    Lowercase, transliterate, strip everything but letters and digits, then apply
    the spelling foldings. `"Sandhigata Vāta"`, `"संधिगत वात"` and
    `"sandhigat vaat"` all fold to the same key.
    """
    lowered = transliterate(text.lower())
    cleaned = "".join(ch if ch.isalnum() else " " for ch in lowered)
    collapsed = " ".join(cleaned.split())
    for source, target in _FOLDINGS:
        collapsed = collapsed.replace(source, target)
    return collapsed


def trigrams(text: str) -> frozenset[str]:
    """Padded character trigrams of the folded form.

    Padding makes prefixes count: a query that is the start of a term scores
    higher than one that merely shares letters with it.
    """
    folded = fold(text).replace(" ", "_")
    if not folded:
        return frozenset()
    padded = f"__{folded}__"
    return frozenset(padded[i : i + 3] for i in range(len(padded) - 2))


def similarity(left: str, right: str) -> float:
    """Jaccard similarity of trigram sets, 0.0..1.0.

    Exact folded equality short-circuits to 1.0 so an exact match always outranks
    a merely similar one, whatever the trigram arithmetic says.
    """
    left_folded, right_folded = fold(left), fold(right)
    if not left_folded or not right_folded:
        return 0.0
    if left_folded == right_folded:
        return 1.0
    a, b = trigrams(left), trigrams(right)
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    if intersection == 0:
        return 0.0
    return round(intersection / len(a | b), 4)


@dataclass(frozen=True, slots=True)
class Candidate:
    """One searchable term."""

    code: str
    display: str
    system: str
    #: Alternative spellings and vernacular names, all searched.
    synonyms: tuple[str, ...] = ()
    definition: str | None = None


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    """A candidate with its score and the term that produced it."""

    candidate: Candidate
    score: float
    matched_on: str

    @property
    def code(self) -> str:
        return self.candidate.code

    @property
    def system(self) -> str:
        return self.candidate.system


def score_candidate(query: str, candidate: Candidate) -> ScoredCandidate:
    """Best-scoring term of a candidate against `query`."""
    best_score = 0.0
    best_term = candidate.display
    for term in (candidate.display, candidate.code, *candidate.synonyms):
        score = similarity(query, term)
        if score > best_score:
            best_score, best_term = score, term
    return ScoredCandidate(candidate=candidate, score=best_score, matched_on=best_term)


def search(
    query: str,
    candidates: Iterable[Candidate],
    *,
    systems: Sequence[str] | None = None,
    limit: int = 10,
    minimum_score: float = 0.2,
) -> tuple[ScoredCandidate, ...]:
    """Ranked matches, best first.

    Ties break on system then code so the ordering is total and reproducible —
    two runs of the same query must never return the same set in a different
    order, or the evaluation harness becomes flaky.
    """
    wanted = frozenset(systems) if systems else None
    scored = [
        result
        for candidate in candidates
        if wanted is None or candidate.system in wanted
        if (result := score_candidate(query, candidate)).score >= minimum_score
    ]
    scored.sort(key=lambda r: (-r.score, r.candidate.system, r.candidate.code))
    return tuple(scored[:limit])
