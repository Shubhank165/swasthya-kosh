"""The clinical state machine: order, pathways, preconditions, completion."""

from __future__ import annotations

import itertools
from datetime import date

import pytest

from app.core.content import ClinicalContent
from app.domain.clinical.enums import (
    AnswerShape,
    Certainty,
    FactStatus,
    Section,
    SourceType,
)
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.clinical.provenance import (
    CodedValue,
    DateValue,
    Duration,
    IntakeId,
    Quantity,
    ScaleValue,
    TextValue,
)
from app.domain.statemachine.engine import ClinicalStateMachine, Complete, Step
from app.domain.statemachine.policies import SelectionPolicy
from app.domain.statemachine.selectors import FieldOrigin, build_plan
from tests.conftest import make_fact

_counter = itertools.count(1)


def answer(
    state: PatientIntakeState, concept: str, value: object = None
) -> PatientIntakeState:
    """Record an answer, superseding any live fact for the concept."""
    live = state.fact_for(concept)
    fact = make_fact(
        concept,
        value=value,
        fact_id=f"f{next(_counter)}",
        supersedes=str(live.fact_id) if live else None,
    )
    return state.apply(fact)


@pytest.fixture
def state() -> PatientIntakeState:
    return PatientIntakeState(intake_id=IntakeId("i"))


class TestSelectionOrder:
    def test_the_first_question_is_language(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        step = machine.next_step(state)
        assert isinstance(step, Step)
        assert step.concept == "preferred_language"
        assert step.section is Section.IDENTITY

    def test_identity_precedes_consent_precedes_chief_complaint(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        """Section order is the clinical intake flow, not an implementation
        detail: consent has to be settled before any history is taken."""
        seen: list[str] = []
        for _ in range(8):
            step = machine.next_step(state)
            if isinstance(step, Complete):
                break
            seen.append(step.section.value)
            state = answer(state, step.concept, _plausible(step))
        assert seen.index("identity") < seen.index("consent")
        assert seen.index("consent") < seen.index("chief_complaint")

    def test_every_step_explains_why_it_was_selected(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        """`selection_reason` is what makes the machine auditable rather than
        merely deterministic."""
        step = machine.next_step(state)
        assert isinstance(step, Step)
        assert "required field" in step.selection_reason
        assert step.concept in step.selection_reason

    def test_selection_is_deterministic(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        first = machine.next_step(state)
        second = machine.next_step(state)
        assert isinstance(first, Step) and isinstance(second, Step)
        assert first.concept == second.concept
        assert first.selection_reason == second.selection_reason


class TestPathwayActivation:
    def test_a_chief_complaint_activates_only_its_own_pathway(
        self, machine: ClinicalStateMachine, content: ClinicalContent, state: PatientIntakeState
    ) -> None:
        """Never ask every possible question: chest pain activates the chest-pain
        pathway and nothing else."""
        state = answer(
            state, "chief_complaint", CodedValue(code="chest_pain")
        ).with_pathway("chest_pain", ("cardiovascular", "respiratory"))
        plan = build_plan(state, content.content_set)
        pathways = {p.source_pathway for p in plan if p.origin is FieldOrigin.PATHWAY}
        assert pathways == {"chest_pain"}
        assert "relation_to_meals" in {p.concept for p in plan}
        assert "morning_stiffness" not in {p.concept for p in plan}

    def test_an_unmatched_complaint_falls_back_rather_than_asking_nothing(
        self, content: ClinicalContent, state: PatientIntakeState
    ) -> None:
        pathway = content.pathways.match_or_fallback("some_unmapped_complaint")
        assert pathway.pathway_id == "general_follow_up"
        assert pathway.required_fields

    def test_the_pathway_pulls_in_its_red_flag_screen_and_ros_groups(
        self, content: ClinicalContent, state: PatientIntakeState
    ) -> None:
        state = state.with_pathway("chest_pain", ("cardiovascular", "respiratory"))
        state = answer(state, "chief_complaint", CodedValue(code="chest_pain"))
        plan = build_plan(state, content.content_set)
        origins = {p.origin for p in plan}
        assert FieldOrigin.RED_FLAG_SCREEN in origins
        assert FieldOrigin.REVIEW_OF_SYSTEMS in origins
        assert "diaphoresis" in {p.concept for p in plan}

    def test_a_concept_asked_by_the_pathway_is_not_asked_again_by_ros(
        self, content: ClinicalContent, state: PatientIntakeState
    ) -> None:
        state = state.with_pathway("chest_pain", ("cardiovascular", "respiratory"))
        plan = build_plan(state, content.content_set)
        concepts = [p.concept for p in plan]
        assert len(concepts) == len(set(concepts))


class TestPreconditions:
    def test_a_field_whose_precondition_fails_is_not_asked(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        """A male patient is never asked about pregnancy, and the record says
        why rather than leaving a hole."""
        state = answer(state, "sex", CodedValue(code="male"))
        state = answer(state, "age", Quantity(34, "years"))
        pending = {concept for (concept, _reason) in _pending(machine, state)}
        assert "pregnancy" in pending

    def test_a_satisfied_precondition_opens_the_field(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        state = answer(state, "sex", CodedValue(code="female"))
        state = answer(state, "age", Quantity(28, "years"))
        pending = {concept for (concept, _reason) in _pending(machine, state)}
        assert "pregnancy" not in pending

    def test_the_failing_precondition_is_recorded_as_the_reason(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        state = answer(state, "sex", CodedValue(code="male"))
        state = answer(state, "age", Quantity(34, "years"))
        reasons = {c: r for c, r in _pending(machine, state)}
        assert "sex" in reasons["pregnancy"]

    def test_a_dependent_field_closes_when_its_parent_is_denied(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        """No operation means no year-of-operation question. It is recorded
        NOT_APPLICABLE, not left as a gap."""
        denied = state.apply(
            make_fact(
                "past_surgery",
                status=FactStatus.ABSENT,
                section=Section.PAST_SURGICAL,
                fact_id="ps_no",
            )
        )
        assert "past_surgery_year" in {c for c, _ in _pending(machine, denied)}

    def test_a_dependent_field_opens_when_its_parent_is_affirmed(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        affirmed = state.apply(
            make_fact(
                "past_surgery",
                status=FactStatus.PRESENT,
                section=Section.PAST_SURGICAL,
                fact_id="ps_yes",
            )
        )
        assert "past_surgery_year" not in {c for c, _ in _pending(machine, affirmed)}


class TestPriorRecordConfirmation:
    def test_a_prior_record_fact_is_re_confirmed_not_asked_cold(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        """Asking a returning diabetic "do you have diabetes?" reads as though
        the hospital lost their file, and invites a wrong answer."""
        state = state.apply(
            make_fact(
                "known_diabetes",
                source_type=SourceType.PRIOR_RECORD,
                certainty=Certainty.CONFIRMED,
                section=Section.PAST_MEDICAL,
                display="Diabetes",
                fact_id="prior1",
            )
        )
        state = _fill_until(machine, state, "known_diabetes")
        step = machine.next_step(state)
        assert isinstance(step, Step)
        assert step.concept == "known_diabetes"
        assert step.is_confirmation
        assert step.answer.shape is AnswerShape.CONFIRMATION
        assert "Our record shows" in step.question
        assert "Diabetes" in step.question
        assert "confirming existing prior_record fact" in step.selection_reason

    def test_a_confirmed_prior_record_fact_is_not_asked_again(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        fact = make_fact(
            "known_diabetes",
            source_type=SourceType.PRIOR_RECORD,
            section=Section.PAST_MEDICAL,
            fact_id="prior1",
        )
        state = state.apply(fact)
        from app.domain.clinical.provenance import FactId

        state = state.apply(
            fact.confirmed_by_patient(
                new_fact_id=FactId("prior2"), recorded_at=fact.recorded_at
            )
        )
        state = _fill_until(machine, state, "known_diabetes")
        step = machine.next_step(state)
        assert not (isinstance(step, Step) and step.concept == "known_diabetes")

    def test_a_yes_no_answer_of_unknown_still_settles_the_field(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        """"I don't know whether I'm diabetic" is a captured answer. Treating it
        as a gap would send the kiosk round in circles."""
        state = state.apply(
            make_fact(
                "known_diabetes",
                status=FactStatus.UNKNOWN,
                section=Section.PAST_MEDICAL,
                fact_id="dk",
            )
        )
        state = _fill_until(machine, state, "known_diabetes")
        step = machine.next_step(state)
        assert not (isinstance(step, Step) and step.concept == "known_diabetes")


class TestCompletion:
    def test_complete_is_only_emitted_when_every_required_field_is_settled(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        """Never on a model's judgement, and never on a time limit alone."""
        result = _run_to_completion(machine, state)
        assert isinstance(result.step, Complete)
        assert result.step.required_settled == result.step.required_total
        assert "all required fields settled" in result.step.reason

    def test_an_unanswered_required_field_prevents_completion(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        result = _run_to_completion(machine, state, skip={"drug_allergy"})
        assert isinstance(result.step, Step)

    def test_a_declined_field_does_not_block_completion(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        """A patient may refuse a question. That is a settled outcome, recorded
        as a refusal — not a gap the kiosk loops on forever."""
        result = _run_to_completion(machine, state, decline={"tobacco_use"})
        assert isinstance(result.step, Complete)
        assert "1 declined by patient" in result.step.reason

    def test_the_optional_budget_bounds_optional_questions_only(
        self, content: ClinicalContent, state: PatientIntakeState
    ) -> None:
        machine = ClinicalStateMachine(
            content.content_set, SelectionPolicy(max_optional_fields=0)
        )
        result = _run_to_completion(machine, state)
        assert isinstance(result.step, Complete)
        assert result.step.optional_asked == 0
        # Every required field was still asked despite the zero optional budget.
        assert result.step.required_settled == result.step.required_total

    def test_a_full_run_asks_a_bounded_number_of_questions(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        """An intake a patient can actually finish in a waiting room."""
        result = _run_to_completion(machine, state)
        assert 20 <= result.asked <= 80


# --- helpers -----------------------------------------------------------------


class _Run:
    def __init__(self, step: Step | Complete, asked: int, concepts: list[str]) -> None:
        self.step = step
        self.asked = asked
        self.concepts = concepts


def _plausible(step: Step) -> object:
    """A valid answer for whatever shape the step asks for."""
    shape = step.answer.shape
    if shape in {AnswerShape.SINGLE_CHOICE, AnswerShape.MULTI_CHOICE, AnswerShape.CONFIRMATION}:
        options = [o for o in step.answer.options if o != "unknown"] or list(step.answer.options)
        return CodedValue(code=options[0])
    if shape is AnswerShape.SCALE:
        return ScaleValue(5, step.answer.minimum or 0, step.answer.maximum or 10)
    if shape is AnswerShape.DURATION:
        return Duration(3, "days")
    if shape is AnswerShape.QUANTITY:
        return Quantity(38, step.answer.unit or "unit")
    if shape is AnswerShape.DATE:
        return DateValue(date(2019, 1, 1), precision="year")
    if shape is AnswerShape.YES_NO_UNKNOWN:
        # `None` becomes UNKNOWN, which is a captured answer — the machine must
        # not loop on it.
        return None
    return TextValue("recorded")


def _pending(
    machine: ClinicalStateMachine, state: PatientIntakeState
) -> list[tuple[str, str]]:
    return [(planned.concept, reason) for planned, reason in machine.pending_not_applicable(state)]


def _fill_until(
    machine: ClinicalStateMachine, state: PatientIntakeState, target: str, limit: int = 60
) -> PatientIntakeState:
    """Answer questions until `target` is the next one."""
    for _ in range(limit):
        step = machine.next_step(state)
        if isinstance(step, Complete) or step.concept == target:
            return state
        state = answer(state, step.concept, _plausible(step))
    return state


def _run_to_completion(
    machine: ClinicalStateMachine,
    state: PatientIntakeState,
    *,
    skip: set[str] | None = None,
    decline: set[str] | None = None,
    limit: int = 120,
) -> _Run:
    skip = skip or set()
    decline = decline or set()
    asked = 0
    concepts: list[str] = []
    for _ in range(limit):
        step = machine.next_step(state)
        if isinstance(step, Complete):
            return _Run(step, asked, concepts)
        asked += 1
        concepts.append(step.concept)
        if step.concept in skip:
            return _Run(step, asked, concepts)
        if step.concept in decline:
            state = state.with_declined(step.concept)
            continue
        # Record NOT_APPLICABLE facts the way the service does, so the plan
        # settles rather than looping on a gated field.
        for planned, _reason in machine.pending_not_applicable(state):
            state = state.apply(
                make_fact(
                    planned.concept,
                    status=FactStatus.NOT_APPLICABLE,
                    section=planned.section,
                    source_type=SourceType.DERIVED,
                    fact_id=f"na_{planned.concept}",
                )
            )
        if state.fact_for(step.concept) is not None and state.is_settled(step.concept):
            continue
        state = answer(state, step.concept, _plausible(step))
        if step.concept == "chief_complaint":
            state = state.with_pathway("fever", ("respiratory", "gi", "genitourinary", "skin"))
    step = machine.next_step(state)
    return _Run(step, asked, concepts)
