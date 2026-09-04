"""Vocabulary the report may never contain.

Carried across unchanged from the previous build's summary templates, which is
the one part of that module worth keeping verbatim: the list was assembled by
reading what a generated intake summary is tempted to say.

The report is built by template, so none of these can appear by accident — a
template cannot hallucinate. The scan exists anyway, as a standing assertion
that stays true if anyone ever wires a model into this path.
"""

from __future__ import annotations

#: Phrasing that turns a statement into clinical advice.
ADVICE_PATTERNS: tuple[str, ...] = (
    "you should take",
    "you must take",
    "you should stop",
    "we recommend",
    "i recommend",
    "you are advised",
    "prescribed for you",
    "treatment plan",
    "start taking",
    "stop taking",
)

#: Phrasing that asserts an interpretation of the patient's findings.
INTERPRETATION_PATTERNS: tuple[str, ...] = (
    "you are suffering",
    "diagnosis is",
    "you have been diagnosed",
    "likely due to",
    "probably due to",
    "consistent with",
    "suggestive of",
    "rule out",
    "indicative of",
    "points towards",
)

#: Named conditions and second-person assertions.
#:
#: Banned in *output*. They cannot be banned in a question — "has a doctor ever
#: told you that you have diabetes?" is a legitimate past-medical question and
#: the disease name is doing honest work there. In a generated report the same
#: phrase would be the system asserting a diagnosis.
ASSERTION_PATTERNS: tuple[str, ...] = (
    "you have",
    "you are having",
    "diagnosed with",
    "myocardial infarction",
    "heart attack",
    "appendicitis",
    "stroke",
    "sepsis",
    "cancer",
)

FORBIDDEN_PATTERNS: tuple[str, ...] = (
    *ASSERTION_PATTERNS,
    *ADVICE_PATTERNS,
    *INTERPRETATION_PATTERNS,
)


def find_unsupported_assertions(text: str) -> tuple[str, ...]:
    """Every forbidden phrase in `text`. The target is always the empty tuple."""
    lowered = text.lower()
    return tuple(pattern for pattern in FORBIDDEN_PATTERNS if pattern in lowered)
