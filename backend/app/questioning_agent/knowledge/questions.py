"""The question bank, loaded from `clinical/questioning/questions/`.

**No text passes through here.** A question in this registry is an id, an answer
type, the slots it fills and the conditions under which it makes sense. What a
patient reads comes from the localization layer keyed on the same id — which is
what lets the same engine run in nine languages without a branch anywhere in it
(§26).

Every question is checked against the slot registry at load time. A question
extracting a slot that does not exist would otherwise be a question asked
forever, since the slot it targets never becomes known.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.questioning_agent.core.enums import AnswerType
from app.questioning_agent.core.schemas import Condition, Question
from app.questioning_agent.knowledge.information_schema import ContentError, SlotRegistry


class QuestionBank:
    """Every question, indexed for the two lookups the selector makes."""

    def __init__(self, questions: dict[str, Question]) -> None:
        self._questions = questions
        self._fixed = tuple(
            sorted(
                (q for q in questions.values() if q.fixed_order is not None),
                key=lambda q: q.fixed_order or 0,
            )
        )
        self._adaptive = tuple(q for q in questions.values() if q.fixed_order is None)

    def __len__(self) -> int:
        return len(self._questions)

    def __contains__(self, question_id: object) -> bool:
        return question_id in self._questions

    def get(self, question_id: str) -> Question | None:
        return self._questions.get(question_id)

    def require(self, question_id: str) -> Question:
        question = self._questions.get(question_id)
        if question is None:
            raise ContentError(f"unknown question {question_id!r}")
        return question

    @property
    def all(self) -> tuple[Question, ...]:
        return tuple(self._questions.values())

    @property
    def fixed(self) -> tuple[Question, ...]:
        """The opening questions, in the order they must be asked."""
        return self._fixed

    @property
    def adaptive(self) -> tuple[Question, ...]:
        """Everything the selector may choose from."""
        return self._adaptive

    @classmethod
    def load(cls, directory: Path, slots: SlotRegistry) -> QuestionBank:
        questions: dict[str, Question] = {}
        files = sorted((directory / "questions").glob("*.yaml"))
        if not files:
            raise ContentError(f"{directory / 'questions'} holds no question files")

        for path in files:
            for entry in _read(path).get("questions") or []:
                question = _question(entry, path)
                if question.id in questions:
                    raise ContentError(f"{path}: question {question.id!r} is defined twice")
                _check_slots(question, slots, path)
                questions[question.id] = question

        _check_fixed(questions, directory)
        return cls(questions)


def _read(path: Path) -> dict[str, Any]:
    try:
        body = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContentError(f"{path}: {exc}") from exc
    if not isinstance(body, dict):
        raise ContentError(f"{path}: expected a mapping at the top level")
    return body


def _question(entry: Any, path: Path) -> Question:
    if not isinstance(entry, dict) or not entry.get("id"):
        raise ContentError(f"{path}: a question has no id")
    question_id = str(entry["id"])
    try:
        return Question(
            id=question_id,
            answer_type=AnswerType(str(entry["answer_type"])),
            extracts=tuple(str(s) for s in entry["extracts"]),
            requires=_condition(entry.get("requires"), path, question_id),
            priority=int(entry.get("priority", 5)),
            burden=int(entry.get("burden", 1)),
            options=tuple(str(o) for o in entry.get("options") or ()),
            options_from=entry.get("options_from"),
            unit=entry.get("unit"),
            units=tuple(str(u) for u in entry.get("units") or ()),
            minimum=entry.get("minimum"),
            maximum=entry.get("maximum"),
            fixed_order=entry.get("fixed_order"),
            domains=tuple(str(d) for d in entry.get("domains") or ()),
            current_state=bool(entry.get("current_state", False)),
        )
    except ContentError:
        raise
    except Exception as exc:
        raise ContentError(f"{path}: question {question_id!r}: {exc}") from exc


def _condition(raw: Any, path: Path, question_id: str) -> Condition | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ContentError(f"{path}: {question_id}: `requires` is not a mapping")
    try:
        return Condition(
            slot=raw.get("slot"),
            equals=raw.get("equals"),
            any_of=tuple(str(v) for v in raw.get("any_of") or ()),
            known=raw.get("known"),
            domain_active=raw.get("domain_active"),
            all=tuple(_leaf(c, path, question_id) for c in raw.get("all") or ()),
            any=tuple(_leaf(c, path, question_id) for c in raw.get("any") or ()),
        )
    except ContentError:
        raise
    except Exception as exc:
        raise ContentError(f"{path}: {question_id}: bad `requires`: {exc}") from exc


def _leaf(raw: Any, path: Path, question_id: str) -> Condition:
    condition = _condition(raw, path, question_id)
    if condition is None:
        raise ContentError(f"{path}: {question_id}: an empty condition inside all/any")
    return condition


def _check_slots(question: Question, slots: SlotRegistry, path: Path) -> None:
    """Every slot a question claims to fill has to exist.

    A question naming a slot the registry does not carry can never satisfy the
    thing it was written for, so the selector offers it, the patient answers it,
    and it comes back round because the slot it targets is still unknown. That
    is a loop, and it is silent.

    `*` and `routing.*` are the two exceptions: the first is resolved against
    the active domains at selection time, and the second is the engine's own
    bookkeeping rather than clinical information.
    """
    for target in question.extracts:
        if target.startswith("*."):
            local = target.split(".", 1)[1]
            if not any(s.id.endswith(f".{local}") for s in slots.all):
                raise ContentError(
                    f"{path}: {question.id} extracts {target!r}, but no domain has a "
                    f"{local!r} slot"
                )
            continue
        if target.startswith("routing."):
            continue
        if target not in slots:
            raise ContentError(f"{path}: {question.id} extracts unknown slot {target!r}")


def _check_fixed(questions: dict[str, Question], directory: Path) -> None:
    """Exactly three fixed questions, numbered 1, 2, 3 — §6."""
    orders = sorted(q.fixed_order for q in questions.values() if q.fixed_order is not None)
    if orders != [1, 2, 3]:
        raise ContentError(
            f"{directory}: the fixed questions must be numbered 1, 2, 3; found {orders}"
        )


__all__ = ["QuestionBank"]
