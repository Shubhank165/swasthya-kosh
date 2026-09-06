"""Question text, per language — §22, §26.

`question_id` is the identity; the text is presentation. Nothing in the engine
branches on language, because nothing in the engine reads text: the selector
scores ids, the dependency evaluator reads slots, and this is the only module
that knows what a sentence looks like.

**A missing string is fatal at load time.** Flutter's own behaviour — and
everybody else's — is to fall back to the template locale, which for a clinical
questionnaire means a Tamil speaker being shown an English question in the
middle of a Tamil screen and answering it. A record then says they answered
something they may not have understood, which is worse than not asking at all.
So the loader refuses a bank with a hole in it, and the consistency test refuses
one with English sitting in another language's file.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.questioning_agent.knowledge.information_schema import ContentError
from app.questioning_agent.localization.languages import LANGUAGES


class Localization:
    """Every string, keyed by id and language."""

    def __init__(self, banks: dict[str, dict[str, dict[str, str]]]) -> None:
        self._banks = banks

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(self._banks)

    def question_text(self, question_id: str, language: str) -> str:
        return self._lookup("questions", question_id, language)

    def option_text(self, option_id: str, language: str) -> str:
        return self._lookup("options", option_id, language)

    def has_question(self, question_id: str, language: str) -> bool:
        return question_id in self._banks.get(language, {}).get("questions", {})

    def has_option(self, option_id: str, language: str) -> bool:
        return option_id in self._banks.get(language, {}).get("options", {})

    def question_ids(self, language: str) -> frozenset[str]:
        return frozenset(self._banks.get(language, {}).get("questions", {}))

    def option_ids(self, language: str) -> frozenset[str]:
        return frozenset(self._banks.get(language, {}).get("options", {}))

    def _lookup(self, kind: str, key: str, language: str) -> str:
        bank = self._banks.get(language)
        if bank is None:
            raise ContentError(f"no question bank for {language!r}")
        text = bank.get(kind, {}).get(key)
        if not text:
            # No fallback. See the module docstring — this is the whole point.
            raise ContentError(f"{language}: no {kind[:-1]} text for {key!r}")
        return text

    @classmethod
    def load(cls, directory: Path) -> Localization:
        banks: dict[str, dict[str, dict[str, str]]] = {}
        for language in LANGUAGES:
            path = directory / "localization" / f"questions_{language}.json"
            if not path.exists():
                raise ContentError(f"{path} does not exist; {language} has no questions")
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ContentError(f"{path}: {exc}") from exc
            if not isinstance(body, dict):
                raise ContentError(f"{path}: expected an object")
            banks[language] = {
                "questions": {str(k): str(v) for k, v in (body.get("questions") or {}).items()},
                "options": {str(k): str(v) for k, v in (body.get("options") or {}).items()},
            }
        return cls(banks)


__all__ = ["Localization"]
