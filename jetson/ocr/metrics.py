"""Scoring for OCR output.

CER is the primary number: for Devanagari, a word-level score punishes a single wrong matra as
harshly as a completely wrong word, which hides real differences between models. WER is reported
alongside because a prescription is read as words, not characters.
"""

from __future__ import annotations

import re
import unicodedata

# Devanagari danda and double danda, plus the usual Latin punctuation, carry no clinical meaning.
PUNCTUATION = re.compile(r"[।॥.,;:!?'\"()\[\]{}<>/\\|`~@#$%^&*_+=—–-]+")
WHITESPACE = re.compile(r"\s+")
# A document model returns structure - HTML tables, markdown headings - and that markup is not a
# reading error. Counting it as one made PaddleOCR-VL score CER 0.63 on a lab report whose every
# value, unit and reference range it had actually read correctly.
MARKUP = re.compile(r"<[^>]{0,80}>|^#{1,6}\s|\*{1,3}", re.MULTILINE)


def normalize(text: str) -> str:
    """Canonical form for comparison.

    NFC matters for Devanagari: the same visible word can be encoded with composed or decomposed
    matras, and comparing raw code points would report errors a reader cannot see.
    """

    text = unicodedata.normalize("NFC", text)
    text = MARKUP.sub(" ", text)
    text = PUNCTUATION.sub(" ", text)
    return WHITESPACE.sub(" ", text).strip()


def levenshtein(a: list[str] | str, b: list[str] | str) -> int:
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, item_a in enumerate(a, start=1):
        current = [i]
        for j, item_b in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,  # deletion
                    current[j - 1] + 1,  # insertion
                    previous[j - 1] + (item_a != item_b),  # substitution
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(reference: str, hypothesis: str) -> float:
    reference, hypothesis = normalize(reference), normalize(hypothesis)
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return levenshtein(reference, hypothesis) / len(reference)


def word_error_rate(reference: str, hypothesis: str) -> float:
    reference_words = normalize(reference).split()
    hypothesis_words = normalize(hypothesis).split()
    if not reference_words:
        return 0.0 if not hypothesis_words else 1.0
    return levenshtein(reference_words, hypothesis_words) / len(reference_words)


def keyword_recall_fuzzy(
    reference_keywords: list[str],
    hypothesis: str,
    tolerance: float = 0.25,
) -> float:
    """Share of critical tokens recoverable if the text is matched against a vocabulary.

    Exact matching scores `पेरासीरामेल` as a total miss when the truth is `पेरासीटामोल` - one
    character out. A production pipeline resolves that against a medicine list, so this reports
    what a dictionary lookup could still rescue. It is the optimistic bound; `keyword_recall` is
    the pessimistic one, and the honest answer lies between them.
    """

    if not reference_keywords:
        return float("nan")
    text = normalize(hypothesis).lower()
    words = text.split()
    found = 0
    for keyword in reference_keywords:
        target = normalize(keyword).lower()
        # An exact hit counts first. Window alignment can miss a multi-word keyword that is
        # plainly present as a substring, which made the fuzzy score come out BELOW the exact
        # one - impossible for a superset, and a sign the window search alone is not enough.
        if target in text:
            found += 1
            continue
        span = len(target.split())
        budget = max(1, int(len(target) * tolerance))
        windows = (" ".join(words[i : i + span]) for i in range(max(1, len(words) - span + 1)))
        if any(levenshtein(target, window) <= budget for window in windows):
            found += 1
    return found / len(reference_keywords)


def keyword_recall(reference_keywords: list[str], hypothesis: str) -> float:
    """Share of clinically critical tokens (a drug, a dose, a date) that survived recognition.

    A model can score a respectable CER while dropping the one token that matters, so the
    benchmark tracks these separately rather than trusting an average.
    """

    if not reference_keywords:
        return float("nan")
    text = normalize(hypothesis).lower()
    found = sum(1 for keyword in reference_keywords if normalize(keyword).lower() in text)
    return found / len(reference_keywords)
