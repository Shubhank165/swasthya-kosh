"""Which question comes next, and why — §31.

The claim under test is not "it asks good questions" — that is a clinical
judgement and it is on the review queue. It is narrower and checkable: the
engine asks about what the patient said is wrong, does not ask about what they
did not, does not ask twice, and stops.
"""

from __future__ import annotations

import pytest

from app.questioning_agent.core.agent import QuestioningAgent
from app.questioning_agent.core.patient_state import PatientState
from tests.questioning.conftest import ask_all, started


class TestTheFixedThree:
    """§6. Routing, before anything adaptive, in order."""

    def test_they_come_first_and_in_order(self, agent: QuestioningAgent) -> None:
        state = PatientState()
        seen = []
        for _ in range(3):
            turn = agent.next(state, language="en")
            assert turn is not None
            seen.append(turn.id)
            # "fever" answers all three: a complaint, the chief one, and a
            # timeline the parser will not read — which is fine, this test is
            # about the order they are put in.
            agent.answer(state, turn, "fever", language="en")
        assert seen == ["fixed.complaints", "fixed.chief_complaint", "fixed.timeline"]

    def test_the_second_offers_back_what_the_first_collected(
        self, agent: QuestioningAgent
    ) -> None:
        """Re-offering all fifteen would be asking somebody to re-read a list
        they have only this moment finished reading."""
        state = PatientState()
        first = agent.next(state, language="en")
        assert first is not None
        agent.answer(state, first, "fever, headache", language="en")

        second = agent.next(state, language="en")
        assert second is not None
        assert [o for o, _ in second.options] == ["fever", "headache"]

    def test_nothing_adaptive_jumps_the_queue(self, agent: QuestioningAgent) -> None:
        state = PatientState()
        turn = agent.next(state, language="en")
        assert turn is not None and turn.question.fixed_order == 1


class TestItAsksAboutWhatIsWrong:
    @pytest.mark.parametrize(
        ("complaints", "expected", "forbidden"),
        [
            (["fever"], "fever.", "headache."),
            (["headache"], "headache.", "fever."),
            (["bleeding"], "bleeding.", "skin."),
            (["respiratory"], "respiratory.", "urinary."),
            (["joint"], "joint.", "menstrual."),
        ],
    )
    def test_only_the_active_domain(
        self,
        agent: QuestioningAgent,
        complaints: list[str],
        expected: str,
        forbidden: str,
    ) -> None:
        """§9. "How high did your temperature get" asked of somebody who never
        mentioned fever is a question that invents a symptom by asking it."""
        state = started(agent, complaints)
        asked = ask_all(agent, state, {}, limit=25)
        assert any(q.startswith(expected) for q in asked), asked
        assert not any(q.startswith(forbidden) for q in asked), asked

    def test_several_unrelated_complaints_all_get_asked_about(
        self, agent: QuestioningAgent
    ) -> None:
        state = started(agent, ["fever", "bowel", "skin"], chief="bowel")
        asked = ask_all(agent, state, {}, limit=40)
        for domain in ("fever.", "bowel.", "skin."):
            assert any(q.startswith(domain) for q in asked), (domain, asked)

    def test_the_chief_complaint_is_asked_about_first(
        self, agent: QuestioningAgent
    ) -> None:
        """What the patient said was worst gets asked about first. It is both
        clinically right and the thing that makes the interview feel like it is
        listening."""
        state = started(agent, ["fever", "bleeding"], chief="bleeding")
        asked = ask_all(agent, state, {}, limit=40)
        first_bleeding = next(i for i, q in enumerate(asked) if q.startswith("bleeding."))
        first_fever = next(i for i, q in enumerate(asked) if q.startswith("fever."))
        assert first_bleeding < first_fever, asked


class TestPrerequisites:
    def test_a_dependent_question_waits_for_what_it_depends_on(
        self, agent: QuestioningAgent
    ) -> None:
        """`fever.maximum_temperature` requires `fever.measured`."""
        state = started(agent, ["fever"])
        asked = ask_all(agent, state, {"fever.measured": "yes"}, limit=30)
        assert "fever.measured" in asked
        assert "fever.maximum_temperature" in asked
        assert asked.index("fever.measured") < asked.index("fever.maximum_temperature")

    def test_a_refused_prerequisite_closes_the_question(
        self, agent: QuestioningAgent
    ) -> None:
        """No thermometer, no reading to ask for."""
        state = started(agent, ["fever"])
        asked = ask_all(agent, state, {"fever.measured": "no"}, limit=30)
        assert "fever.maximum_temperature" not in asked

    def test_sputum_colour_waits_on_a_productive_cough(
        self, agent: QuestioningAgent
    ) -> None:
        state = started(agent, ["respiratory"])
        dry = ask_all(agent, state, {"respiratory.cough_type": "dry"}, limit=30)
        assert "respiratory.sputum_colour" not in dry

        state = started(agent, ["respiratory"])
        wet = ask_all(agent, state, {"respiratory.cough_type": "productive"}, limit=30)
        assert "respiratory.sputum_colour" in wet

    def test_pregnancy_is_asked_only_where_it_applies(
        self, agent: QuestioningAgent
    ) -> None:
        state = started(agent, ["fever"])
        asked = ask_all(agent, state, {"history.sex": "male"}, limit=30)
        assert "history.pregnancy" not in asked


class TestItDoesNotRepeatItself:
    def test_nothing_is_asked_twice(self, agent: QuestioningAgent) -> None:
        state = started(agent, ["fever", "headache"])
        asked = ask_all(agent, state, {}, limit=60)
        # A clarification re-asks by design; everything else appears once.
        repeated = [q for q in set(asked) if asked.count(q) > 1]
        assert not repeated, repeated

    def test_a_slot_already_known_is_not_asked_for(
        self, agent: QuestioningAgent
    ) -> None:
        """The timeline sentence fills duration and progression, so the
        follow-ups that only fill those must not be offered."""
        state = started(
            agent, ["fever"], timeline="started three days ago and getting worse"
        )
        assert state.knows("fever.duration")
        assert state.knows("fever.progression")
        asked = ask_all(agent, state, {}, limit=30)
        assert "general.duration" not in asked
        assert "general.progression" not in asked


class TestItStops:
    def test_it_ends_rather_than_asking_everything(
        self, agent: QuestioningAgent
    ) -> None:
        """There is no question budget. The interview ends when nothing left is
        worth the asking, which is what makes it short for a simple problem."""
        state = started(agent, ["sleep"])
        asked = ask_all(agent, state, {}, limit=200)
        assert len(asked) <= 25, len(asked)
        assert agent.next(state, language="en") is None

    def test_one_simple_problem_is_shorter_than_four(
        self, agent: QuestioningAgent
    ) -> None:
        simple = ask_all(agent, started(agent, ["sleep"]), {}, limit=200)
        complex_ = ask_all(
            agent,
            started(agent, ["fever", "respiratory", "digestive", "joint"]),
            {},
            limit=200,
        )
        assert len(simple) < len(complex_)


class TestItIsDeterministic:
    def test_the_same_state_gives_the_same_question(
        self, agent: QuestioningAgent
    ) -> None:
        """The acceptance criterion the whole design rests on."""
        first = ask_all(agent, started(agent, ["fever", "headache"]), {}, limit=25)
        second = ask_all(agent, started(agent, ["fever", "headache"]), {}, limit=25)
        assert first == second


class TestItExplainsItself:
    def test_every_decision_carries_its_reasons(self, agent: QuestioningAgent) -> None:
        """§30. Not exposed to the patient; available for debugging, and the
        thing that makes a clinician's disagreement actionable."""
        state = started(agent, ["bleeding"])
        turn = agent.next(state, language="en")
        assert turn is not None
        assert turn.decision.reasons
        assert turn.decision.targets
        assert turn.decision.score > 0

    def test_the_reasons_name_the_chief_complaint_when_that_is_why(
        self, agent: QuestioningAgent
    ) -> None:
        state = started(agent, ["fever", "bleeding"], chief="bleeding")
        for _ in range(6):
            turn = agent.next(state, language="en")
            assert turn is not None
            if turn.id.startswith("bleeding."):
                assert any("bleeding" in r for r in turn.decision.reasons)
                return
            agent.skip(state, turn)
        pytest.fail("no bleeding question was offered in the first six")
