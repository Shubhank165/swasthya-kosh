"""Prerequisites, compression and the safety layer — §31.

Three claims that share a page because they are all about *not* asking:

- a question whose precondition is refused is never asked;
- a question already answered by a merged one is never asked;
- and once a red flag fires, nothing is asked at all.
"""

from __future__ import annotations

from app.questioning_agent.core.agent import QuestioningAgent
from app.questioning_agent.core.patient_state import PatientState
from app.questioning_agent.core.schemas import Condition
from app.questioning_agent.questioning.candidate_generator import candidates
from app.questioning_agent.questioning.dependencies import Tri, evaluate
from tests.questioning.conftest import ask_all, started


class TestThreeValuedConditions:
    """`UNKNOWN` is a real answer and collapsing it either way is a bug.

    Into `NO`: the temperature question is discarded permanently, one turn
    before the patient says they own a thermometer.

    Into `YES`: "how high did your temperature get" is asked of somebody who
    never mentioned a fever, and patients answer questions they are asked.
    """

    def test_an_unknown_slot_is_not_yet_knowable(
        self, agent: QuestioningAgent
    ) -> None:
        state = PatientState()
        condition = Condition(slot="fever.present", equals=True)
        assert evaluate(condition, state) is Tri.UNKNOWN

    def test_a_matching_slot_is_yes(self, agent: QuestioningAgent) -> None:
        state = started(agent, ["fever"])
        assert evaluate(Condition(slot="fever.present", equals=True), state) is Tri.YES

    def test_a_non_matching_slot_is_no(self, agent: QuestioningAgent) -> None:
        state = started(agent, ["fever"])
        assert evaluate(Condition(slot="fever.present", equals=False), state) is Tri.NO

    def test_all_needs_every_part(self, agent: QuestioningAgent) -> None:
        state = started(agent, ["fever"])
        both = Condition(
            all=(
                Condition(slot="fever.present", equals=True),
                Condition(slot="fever.measured", equals=True),
            )
        )
        # One known and true, one not yet asked.
        assert evaluate(both, state) is Tri.UNKNOWN

    def test_any_is_satisfied_by_one(self, agent: QuestioningAgent) -> None:
        state = started(agent, ["fever"])
        either = Condition(
            any=(
                Condition(slot="fever.present", equals=True),
                Condition(slot="bleeding.present", equals=True),
            )
        )
        assert evaluate(either, state) is Tri.YES

    def test_a_domain_condition_reads_the_active_domains(
        self, agent: QuestioningAgent
    ) -> None:
        state = started(agent, ["fever"])
        assert evaluate(Condition(domain_active="fever"), state) is Tri.YES
        assert evaluate(Condition(domain_active="skin"), state) is Tri.NO


class TestCompression:
    """§12. One question where three would do, and no special case for it."""

    def test_a_cross_domain_question_targets_every_active_domain(
        self, agent: QuestioningAgent
    ) -> None:
        state = started(agent, ["fever", "headache", "joint"], timeline="unclear")
        found = {
            candidate.question.id: candidate.targets
            for candidate in candidates(state, agent.bank, agent.slots)
        }
        severity = found["general.severity"]
        assert set(severity) == {
            "fever.severity",
            "headache.severity",
            "joint.severity",
        }

    def test_three_symptoms_do_not_produce_three_onset_questions(
        self, agent: QuestioningAgent
    ) -> None:
        """The §12 example, exactly."""
        state = started(agent, ["fever", "headache", "joint"], timeline="unclear")
        asked = ask_all(agent, state, {"general.onset": "gradual"}, limit=40)
        onset_questions = [q for q in asked if q.endswith(".onset")]
        assert onset_questions == ["general.onset"], onset_questions

    def test_one_answer_fills_the_slot_for_every_active_domain(
        self, agent: QuestioningAgent
    ) -> None:
        state = started(agent, ["fever", "headache", "joint"], timeline="unclear")
        ask_all(agent, state, {"general.onset": "gradual"}, limit=40)
        for domain in ("fever", "headache", "joint"):
            assert state.value(f"{domain}.onset") == "gradual", domain

    def test_a_merged_question_outranks_the_specific_ones(
        self, agent: QuestioningAgent
    ) -> None:
        """Coverage is part of the score, so this falls out of the arithmetic.
        Nothing in the engine knows what "merging" is."""
        from app.questioning_agent.questioning.scoring import score

        state = started(agent, ["fever", "headache", "joint"], timeline="unclear")
        by_id = {c.question.id: c for c in candidates(state, agent.bank, agent.slots)}
        merged = score(by_id["general.severity"], state, agent.slots)
        specific = score(by_id["headache.site"], state, agent.slots)
        assert merged.score > specific.score

    def test_a_domain_that_skips_the_slot_is_left_out(
        self, agent: QuestioningAgent
    ) -> None:
        """`sleep` has no `pattern` slot, so a sleep-only patient never sees the
        pattern question rather than seeing one that cannot be recorded."""
        state = started(agent, ["sleep"], timeline="unclear")
        offered = {c.question.id for c in candidates(state, agent.bank, agent.slots)}
        assert "general.pattern" not in offered


class TestSafetyStopsEverything:
    """§28. A fired rule ends the interview; it does not merely outrank."""

    def test_a_red_flag_ends_the_questionnaire(self, agent: QuestioningAgent) -> None:
        state = started(agent, ["respiratory"])
        asked = ask_all(
            agent, state, {"respiratory.breathlessness": "at_rest"}, limit=40
        )
        assert state.red_flags
        assert agent.next(state, language="en") is None
        assert "respiratory.breathlessness" in asked

    def test_the_label_names_no_condition(self, agent: QuestioningAgent) -> None:
        """It says a human must look now. It does not say what is wrong, and it
        is never shown to the patient as a finding."""
        state = started(agent, ["respiratory"])
        ask_all(agent, state, {"respiratory.breathlessness": "at_rest"}, limit=40)
        flag = state.red_flags[0]
        assert flag.label == "Urgent clinical review criterion triggered"

    def test_blood_in_stool_fires(self, agent: QuestioningAgent) -> None:
        state = started(agent, ["bowel"])
        ask_all(agent, state, {"bowel.blood_in_stool": "yes"}, limit=40)
        assert [f.id for f in state.red_flags] == ["blood_in_stool"]

    def test_an_unknown_slot_never_fires_a_rule(
        self, agent: QuestioningAgent
    ) -> None:
        """A rule fires on what a patient said, not on what they were not asked."""
        state = started(agent, ["respiratory"])
        assert not agent.triage.check(state)

    def test_a_denial_does_not_fire(self, agent: QuestioningAgent) -> None:
        state = started(agent, ["bowel"])
        ask_all(agent, state, {"bowel.blood_in_stool": "no"}, limit=40)
        assert not state.red_flags

    def test_safety_is_not_in_the_scoring(self) -> None:
        """The structural claim, checked structurally: the scoring module does
        not import the safety layer and has no term for it."""
        from app.questioning_agent.questioning import scoring

        source = __import__("inspect").getsource(scoring)
        assert "triage" not in source
        assert "red_flag" not in source
