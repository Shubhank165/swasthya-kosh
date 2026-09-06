"""The languages, and the vocabulary each one parses with.

**One normalisation layer per language, not one with special cases.** The
English parser does not work on Hindi and was never going to: Hindi negates at
the end of the clause, its numerals are different glyphs, and "पेट में जलन" shares
no substring with "burning in the stomach". A single tokeniser with a lookup
table bolted on would be an English parser that sometimes gets other languages
right, which is worse than one that admits it cannot.

So each language brings its own cues, synonyms, numerals and boundaries, loaded
from `clinical/questioning/vocabulary/<lang>.yaml`, and the parsers are
generic machinery over that data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.questioning_agent.interpretation.negation import NegationRules
from app.questioning_agent.knowledge.information_schema import ContentError

#: The nine the app speaks. Kept in step with `app/lib/l10n/strings.dart`, and
#: the localization test fails if a bank is missing one of them.
LANGUAGES: tuple[str, ...] = ("en", "hi", "bn", "ta", "te", "mr", "gu", "kn", "pa")


@dataclass(frozen=True, slots=True)
class Vocabulary:
    """Everything one language's parsers match on."""

    language: str
    affirm: frozenset[str]
    deny: frozenset[str]
    unsure: frozenset[str]
    negation: NegationRules
    #: Number words to values, including the language's own numerals.
    numbers: dict[str, float]
    #: Canonical duration unit to the words meaning it.
    duration_units: dict[str, frozenset[str]]
    #: Fixed temporal expressions to a (value, unit) offset.
    temporal: dict[str, tuple[float, str]]
    #: Hedges. Their presence marks a value approximate rather than exact.
    approximate: frozenset[str]
    #: Severity words to a 0-10 point.
    severity: dict[str, float]
    #: Domain id to the words patients use for it.
    symptoms: dict[str, frozenset[str]]
    #: Option id to the words meaning it, for reading a code out of free text.
    options: dict[str, frozenset[str]] = field(default_factory=dict)
    #: Anatomical site words, for the pain and bleeding descriptions.
    sites: dict[str, frozenset[str]] = field(default_factory=dict)

    def synonyms_for(self, option_id: str) -> frozenset[str]:
        """Every word in this language meaning `option_id`.

        Three tables, one lookup. The domain ids on fixed question 1 are option
        ids *and* symptom names — ticking "fever" and writing "बुखार" are the
        same answer — and keeping the two lists apart meant a Hindi speaker
        could name their complaint in Hindi and have it recognised nowhere.
        """
        empty: frozenset[str] = frozenset()
        return (
            self.options.get(option_id, empty)
            | self.symptoms.get(option_id, empty)
            | self.sites.get(option_id, empty)
        )

    @classmethod
    def load(cls, directory: Path, language: str) -> Vocabulary:
        path = directory / "vocabulary" / f"{language}.yaml"
        if not path.exists():
            raise ContentError(f"{path} does not exist; {language} has no parser")
        body = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(body, dict):
            raise ContentError(f"{path}: expected a mapping")

        negation = body.get("negation") or {}
        return cls(
            language=language,
            affirm=_words(body, "affirm", path),
            deny=_words(body, "deny", path),
            unsure=_words(body, "unsure", path),
            negation=NegationRules(
                cues=frozenset(_lower(negation.get("cues") or ())),
                boundaries=frozenset(_lower(negation.get("boundaries") or ())),
                sentence_final=bool(negation.get("sentence_final", False)),
            ),
            numbers={str(k).lower(): float(v) for k, v in (body.get("numbers") or {}).items()},
            duration_units=_groups(body.get("duration_units") or {}),
            temporal={
                str(k).lower(): (float(v[0]), str(v[1]))
                for k, v in (body.get("temporal") or {}).items()
            },
            approximate=frozenset(_lower(body.get("approximate") or ())),
            severity={
                str(k).lower(): float(v) for k, v in (body.get("severity") or {}).items()
            },
            symptoms=_groups(body.get("symptoms") or {}),
            options=_groups(body.get("options") or {}),
            sites=_groups(body.get("sites") or {}),
        )


def _words(body: dict[str, Any], key: str, path: Path) -> frozenset[str]:
    values = body.get(key)
    if not values:
        raise ContentError(f"{path}: {key} is empty; this language cannot read a yes or a no")
    return frozenset(_lower(values))


def _lower(values: Any) -> list[str]:
    return [str(v).strip().lower() for v in values if str(v).strip()]


def _groups(raw: Any) -> dict[str, frozenset[str]]:
    return {str(key): frozenset(_lower(values or ())) for key, values in (raw or {}).items()}


class Vocabularies:
    """Every language's vocabulary, loaded once."""

    def __init__(self, by_language: dict[str, Vocabulary]) -> None:
        self._by_language = by_language

    def __getitem__(self, language: str) -> Vocabulary:
        vocabulary = self._by_language.get(language)
        if vocabulary is None:
            raise ContentError(f"no vocabulary for {language!r}")
        return vocabulary

    def __contains__(self, language: object) -> bool:
        return language in self._by_language

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(self._by_language)

    @classmethod
    def load(cls, directory: Path) -> Vocabularies:
        return cls({lang: Vocabulary.load(directory, lang) for lang in LANGUAGES})


__all__ = ["LANGUAGES", "Vocabularies", "Vocabulary"]
