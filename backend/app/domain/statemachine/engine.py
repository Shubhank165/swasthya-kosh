"""The clinical state machine.

`next_step` is a pure function of (state, content, policy). It decides *what* is
asked and in what order. A generative model may later re-word the returned
`question` — it never chooses the concept, never reorders the plan, and never
decides that the history is finished.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from app.domain.clinical.enums import AnswerShape, Section
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.ontology.pathway import AnswerSpec
from app.domain.statemachine.policies import DEFAULT_POLICY, SelectionPolicy
from app.domain.statemachine.selectors import (
    ContentSet,
    FieldOrigin,
    PlannedField,
    active_pathway,
    answered_optional_count,
    build_plan,
    inapplicable_fields,
    is_owed,
    needs_confirmation,
    outstanding_optional,
    outstanding_required,
)


@dataclass(frozen=True, slots=True)
class Step:
    """One question, fully specified. This is what the kiosk renders and what a
    voice renderer receives as its single authored turn."""

    concept: str
    question: str
    language: str
    answer: AnswerSpec
    section: Section
    origin: FieldOrigin
    source_pathway: str
    required: bool
    skippable: bool
    #: Why the engine chose this field. Asserted in tests and reported by the
    #: evaluation harness; it is what makes the machine's behaviour auditable.
    selection_reason: str
    #: Options rendered as touch targets, already localised where content exists.
    touch_options: tuple[str, ...] = field(default_factory=tuple)
    #: Populated when the step re-confirms a fact we already hold.
    confirming_value: str | None = None
    #: Prompts in every supported language, for a client that switches mid-session.
    prompts: Mapping[str, str] = field(default_factory=dict)

    @property
    def is_confirmation(self) -> bool:
        return self.answer.shape is AnswerShape.CONFIRMATION


@dataclass(frozen=True, slots=True)
class Complete:
    """No question remains. Emitted only when every required field is settled."""

    reason: str
    required_total: int
    required_settled: int
    optional_asked: int


class StateMachine(Protocol):
    def next_step(self, state: PatientIntakeState) -> Step | Complete: ...


_CONFIRMATION_PROMPTS: Mapping[str, str] = {
    "en": "Our record shows {value}. Is that still correct?",
    "hi": "हमारे रिकॉर्ड में {value} दर्ज है। क्या यह अब भी सही है?",
}

_CONFIRMATION_OPTIONS: Mapping[str, tuple[str, ...]] = {
    "en": ("yes", "no", "not sure"),
    "hi": ("हाँ", "नहीं", "पता नहीं"),
}


class ClinicalStateMachine:
    """Deterministic implementation. No randomness, no clock, no I/O."""

    def __init__(self, content: ContentSet, policy: SelectionPolicy = DEFAULT_POLICY) -> None:
        self._content = content
        self._policy = policy

    @property
    def content(self) -> ContentSet:
        return self._content

    @property
    def policy(self) -> SelectionPolicy:
        return self._policy

    def plan(self, state: PatientIntakeState) -> tuple[PlannedField, ...]:
        """The full ordered field list for this intake. Exposed for coverage."""
        return build_plan(state, self._content)

    def pending_not_applicable(
        self, state: PatientIntakeState
    ) -> tuple[tuple[PlannedField, str], ...]:
        """Owed fields whose precondition fails, paired with the failing reason.

        The caller records these as NOT_APPLICABLE facts before asking anything
        else, so the record says *why* a question was never put.
        """
        plan = self.plan(state)
        return tuple(
            (p, p.field.precondition_reason() or "precondition not satisfied")
            for p in inapplicable_fields(state, plan)
        )

    def next_step(self, state: PatientIntakeState) -> Step | Complete:
        """The next question, or `Complete`.

        Order of resort:
          1. the highest-priority outstanding required field,
          2. an optional field, if policy allows and the budget is not spent,
          3. `Complete`.
        """
        plan = self.plan(state)
        language = self._policy.resolve_language(state.language)

        required = outstanding_required(state, plan)
        if required:
            return self._to_step(state, required[0], language, rank=len(required))

        if self._policy.ask_optional_fields:
            asked = answered_optional_count(state, plan)
            if asked < self._policy.max_optional_fields:
                optional = outstanding_optional(state, plan)
                if optional:
                    return self._to_step(
                        state,
                        optional[0],
                        language,
                        rank=len(optional),
                        optional_budget=self._policy.max_optional_fields - asked,
                    )

        required_fields = tuple(p for p in plan if p.required)
        return Complete(
            reason=self._completion_reason(state, plan),
            required_total=len(required_fields),
            required_settled=sum(1 for p in required_fields if not is_owed(state, p)),
            optional_asked=answered_optional_count(state, plan),
        )

    # --- internals ----------------------------------------------------------

    def _completion_reason(
        self, state: PatientIntakeState, plan: tuple[PlannedField, ...]
    ) -> str:
        pathway = active_pathway(state, self._content)
        pathway_id = pathway.pathway_id if pathway is not None else "none"
        declined = len(state.declined)
        suffix = f"; {declined} declined by patient" if declined else ""
        return (
            f"all required fields settled for pathway '{pathway_id}' "
            f"({len(plan)} fields planned){suffix}"
        )

    def _to_step(
        self,
        state: PatientIntakeState,
        planned: PlannedField,
        language: str,
        *,
        rank: int,
        optional_budget: int | None = None,
    ) -> Step:
        if needs_confirmation(state, planned.concept) and self._policy.confirm_prior_records:
            return self._confirmation_step(state, planned, language)

        pathway_field = planned.field
        reason = (
            f"{'required' if planned.required else 'optional'} field "
            f"'{planned.concept}' in section '{planned.section}' "
            f"from {planned.origin} '{planned.source_pathway}'; "
            f"{rank} field(s) outstanding at this level"
        )
        if optional_budget is not None:
            reason += f"; optional budget remaining {optional_budget}"
        if pathway_field.precondition is not None:
            reason += f"; precondition satisfied: {pathway_field.precondition.describe()}"

        return Step(
            concept=planned.concept,
            question=pathway_field.prompt_for(language),
            language=language,
            answer=pathway_field.answer,
            section=planned.section,
            origin=planned.origin,
            source_pathway=planned.source_pathway,
            required=planned.required,
            skippable=pathway_field.skippable,
            selection_reason=reason,
            touch_options=pathway_field.answer.options,
            prompts=dict(pathway_field.prompts),
        )

    def _confirmation_step(
        self, state: PatientIntakeState, planned: PlannedField, language: str
    ) -> Step:
        """Re-confirm a prior-record fact instead of asking it cold.

        Asking a returning diabetic "do you have diabetes?" reads as though the
        hospital has lost their file, and it invites a wrong answer.
        """
        fact = state.fact_for(planned.concept)
        rendered = (fact.display() if fact is not None else planned.concept.replace("_", " "))
        template = _CONFIRMATION_PROMPTS.get(language, _CONFIRMATION_PROMPTS["en"])
        options = _CONFIRMATION_OPTIONS.get(language, _CONFIRMATION_OPTIONS["en"])
        source = fact.source_type.value if fact is not None else "prior_record"
        return Step(
            concept=planned.concept,
            question=template.format(value=rendered),
            language=language,
            answer=AnswerSpec(shape=AnswerShape.CONFIRMATION, options=options),
            section=planned.section,
            origin=planned.origin,
            source_pathway=planned.source_pathway,
            required=planned.required,
            skippable=planned.field.skippable,
            selection_reason=(
                f"confirming existing {source} fact for '{planned.concept}' "
                "rather than asking an open question"
            ),
            touch_options=options,
            confirming_value=rendered,
            prompts={
                lang: tmpl.format(value=rendered) for lang, tmpl in _CONFIRMATION_PROMPTS.items()
            },
        )
