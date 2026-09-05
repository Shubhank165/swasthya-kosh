"""The question content, as parsed — 2/3 §4.

Pure data. Nothing in this package evaluates a precondition or fires a red flag;
it parses YAML, validates it, and hands back objects the compiler turns into a
bundle. Question selection and red-flag evaluation belong to whichever device is
asking the questions, and putting a second evaluator here would mean two engines
that can disagree — which is worse than one engine, because the disagreement is
invisible until a patient is affected by it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: The answer shapes the app must be able to render. `2/3 §4` fixes this list:
#: an app that meets an `answer_type` outside it records `not_asked` and logs a
#: content-version mismatch rather than crashing, so the compiler must map every
#: authored type onto one of these rather than passing an author's typo through.
AnswerType = Literal[
    "single_choice",
    "multi_choice",
    "yes_no_unknown",
    "number",
    "scale",
    "duration",
    "date",
    "free_text",
]

#: Authored type -> bundle type. `quantity` is the content's name for a numeric
#: answer with a unit; `confirmation` is a two-option choice. Neither is a new
#: shape, and inventing bundle types for them would mean every consumer growing
#: a renderer for a distinction that does not exist.
TYPE_ALIASES: Mapping[str, AnswerType] = {
    "quantity": "number",
    "confirmation": "single_choice",
}


class Condition(BaseModel):
    """One node of the shared expression language.

    Preconditions and red-flag criteria use the same shape, so a reviewer learns
    it once. A node is either a boolean combinator (`all` / `any` / `not`) or a
    leaf comparing one field.

    **The nesting is load-bearing and must not be flattened.** `2/3 §4` shows a
    flat `all` list by way of example, but the authored content is not flat: the
    cardiac rule is `chest_pain AND sudden onset AND (dyspnoea OR diaphoresis)`,
    and the pregnancy precondition is `female AND age >= 12 AND age <= 55`.
    Flattening either would change which patients are asked what, and in the
    cardiac case would drop a critical rule's disjunction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    all_: tuple[Condition, ...] | None = Field(default=None, alias="all")
    any_: tuple[Condition, ...] | None = Field(default=None, alias="any")
    not_: Condition | None = Field(default=None, alias="not")

    field_id: str | None = None
    status: str | None = None
    in_: tuple[str, ...] | None = Field(default=None, alias="in")
    equals: bool | str | float | None = None
    gte: float | None = None
    lte: float | None = None

    def as_bundle(self) -> dict[str, Any]:
        """The wire form, with `None` branches dropped.

        Emitted with the original key names — `all`, `any`, `in` — because the
        app and the Jetson read this, not Python.
        """
        if self.all_ is not None:
            return {"all": [c.as_bundle() for c in self.all_]}
        if self.any_ is not None:
            return {"any": [c.as_bundle() for c in self.any_]}
        if self.not_ is not None:
            return {"not": self.not_.as_bundle()}
        leaf: dict[str, Any] = {"field_id": self.field_id}
        for key, value in (
            ("status", self.status),
            ("in", list(self.in_) if self.in_ is not None else None),
            ("equals", self.equals),
            ("gte", self.gte),
            ("lte", self.lte),
        ):
            if value is not None:
                leaf[key] = value
        return leaf

    def fields_read(self) -> frozenset[str]:
        """Every field this expression depends on.

        Used to check that a red-flag rule only reads fields some question
        actually asks — a rule reading a field nobody is asked can never fire,
        and looks like working safety coverage.
        """
        for branch in (self.all_, self.any_):
            if branch is not None:
                return frozenset().union(*(c.fields_read() for c in branch))
        if self.not_ is not None:
            return self.not_.fields_read()
        return frozenset({self.field_id}) if self.field_id else frozenset()


Condition.model_rebuild()


class Question(BaseModel):
    """One question, in one place in one pathway."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    field_id: str
    section: str
    answer_type: AnswerType
    #: Choice options, or `None` for the types that have none.
    options: tuple[str, ...] | None = None
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    prompts: Mapping[str, str]
    required: bool = True
    allow_skip: bool = True
    #: Every question offers "I don't know". `2/3 §4` makes this unconditional
    #: and it is not a per-question decision: a patient who cannot answer must
    #: always have a way to say so that is not a guess and not a silence.
    allow_unknown: bool = True
    precondition: Condition | None = None
    priority: int = 0
    needs_clinical_review: bool = False
    #: Asked again on a return visit — 2/3 §5 screen 8.
    #:
    #: Only the Ayurveda module uses it today: the full set on a first visit,
    #: and Agni, Nidra and Koshtha again on a return. Which items those are is a
    #: clinical judgement and belongs in the content, not in a list in the app.
    current_state: bool = False

    def as_bundle(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "question_id": self.question_id,
            "field_id": self.field_id,
            "section": self.section,
            "answer_type": self.answer_type,
            "required": self.required,
            "prompts": dict(self.prompts),
            "options": list(self.options) if self.options is not None else None,
            "precondition": (
                self.precondition.as_bundle() if self.precondition else None
            ),
            "allow_skip": self.allow_skip,
            "allow_unknown": self.allow_unknown,
        }
        for key, value in (
            ("unit", self.unit),
            ("min", self.minimum),
            ("max", self.maximum),
        ):
            if value is not None:
                body[key] = value
        return body


class RedFlagRule(BaseModel):
    """A criterion that stops the intake and sends the patient to urgent care.

    `label` is fixed wording that says a human must look now. It never names a
    condition and is never shown to the patient as a finding — the app's urgent
    -care screen has its own bounded wording (`2/3 §6`) and does not render this.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    severity: str
    label: str
    criteria: Condition
    clinical_source: str
    guidance: str | None = None

    @field_validator("clinical_source")
    @classmethod
    def _must_be_sourced(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("a red-flag rule without a clinical_source does not load")
        return value

    def as_bundle(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "criteria": self.criteria.as_bundle(),
        }


class QuestionSet(BaseModel):
    """Everything parsed, before compilation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content_version: str
    languages: tuple[str, ...]
    core: tuple[Question, ...]
    #: Complaint value -> the questions that complaint adds, in order.
    branches: Mapping[str, tuple[Question, ...]]
    ayurveda: tuple[Question, ...]
    red_flags: tuple[RedFlagRule, ...]
    sections: tuple[str, ...]

    def all_questions(self) -> Sequence[Question]:
        seen: dict[str, Question] = {}
        for group in (self.core, *self.branches.values(), self.ayurveda):
            for question in group:
                seen.setdefault(question.question_id, question)
        return list(seen.values())
