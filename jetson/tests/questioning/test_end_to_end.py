"""Whole conversations — §31.

Simulated patients, answering in ordinary language, from the first fixed
question to the case summary. These are the tests that would catch a regression
nothing else notices, because they are the only ones that exercise the loop
rather than its parts.

Each one reads as a transcript on purpose. A test somebody can follow line by
line is a test a clinician can be shown.
"""

from __future__ import annotations

from questioning_agent.core.agent import QuestioningAgent
from questioning_agent.core.enums import Certainty, Provenance
from questioning_agent.core.patient_state import PatientState
from questioning_agent.output.case_summary import render


def run(
    agent: QuestioningAgent,
    script: dict[str, str],
    *,
    language: str = "en",
    limit: int = 60,
) -> PatientState:
    """Walk a whole interview, answering from `script` and skipping the rest."""
    state = PatientState()
    for _ in range(limit):
        turn = agent.next(state, language=language)
        if turn is None:
            break
        reply = script.get(turn.id)
        if reply is None:
            agent.skip(state, turn)
        else:
            agent.answer(state, turn, reply, language=language)
    return state


class TestAFeverAndHeadache:
    """The §37 shape: what brings you in, what is worst, when did it start."""

    SCRIPT = {
        "fixed.complaints": "fever and headache",
        "fixed.chief_complaint": "fever",
        "fixed.timeline": "started about three days ago and it's getting worse",
        "history.age": "34",
        "history.sex": "female",
        "fever.measured": "yes, with a thermometer",
        "fever.maximum_temperature": "102 F",
        "fever.chills": "yes, I get shivering at night",
        "headache.site": "mostly my forehead",
        "general.severity": "7",
        "history.current_medications": "paracetamol, and Giloy kadha in the morning",
        "history.allergies": "none that I know of",
        "ayush.appetite": "poor",
        "ayush.after_eating": "heaviness and bloating",
        "ayush.bowel_habit": "constipated",
        "ayush.sleep_quality": "disturbed",
    }

    def test_the_case_carries_what_the_patient_said(
        self, agent: QuestioningAgent
    ) -> None:
        state = run(agent, self.SCRIPT)

        # One sentence, six slots: onset, duration and progression for both
        # active domains.
        assert state.value("fever.duration")["value"] == 3
        assert state.value("fever.duration")["approximate"] is True
        assert state.value("headache.duration")["value"] == 3
        assert state.value("fever.progression") == "worsening"
        assert state.value("headache.progression") == "worsening"

        # And the temperature, in the unit the patient used.
        assert state.value("fever.maximum_temperature") == {
            "value": 102,
            "unit": "fahrenheit",
        }

    def test_the_summary_separates_what_was_said_from_what_was_read(
        self, agent: QuestioningAgent
    ) -> None:
        """§29. "The patient said three days" and "a parser found three days in
        a sentence" are different claims."""
        summary = agent.summarise(run(agent, self.SCRIPT))
        values = {v.slot: v for section in summary.sections for v in section.values}

        assert values["fever.duration"].provenance is Provenance.SYSTEM_NORMALISED
        assert values["fever.duration"].certainty is Certainty.PROBABLE  # "about"
        assert values["headache.site"].value == "frontal"

    def test_the_raw_answers_are_kept(self, agent: QuestioningAgent) -> None:
        """§20. A practitioner who doubts a value reads the sentence."""
        state = run(agent, self.SCRIPT)
        said = dict(agent.summarise(state).verbatim)
        assert said["fixed.timeline"] == self.SCRIPT["fixed.timeline"]
        assert "Giloy" in said["history.current_medications"]

    def test_it_does_not_diagnose(self, agent: QuestioningAgent) -> None:
        """§29, and the whole point of §1.

        There is no impression, no differential and no advice, because there is
        nowhere in the structure to put one.
        """
        summary = agent.summarise(run(agent, self.SCRIPT))
        text = render(summary, agent.slots).lower()
        for word in ("diagnosis", "likely", "suggests", "probably", "consistent with"):
            assert word not in text, word

    def test_the_practitioner_gets_a_list_of_what_is_theirs(
        self, agent: QuestioningAgent
    ) -> None:
        summary = agent.summarise(run(agent, self.SCRIPT))
        assert "assessment.agni" in summary.clinician_assessed
        assert "assessment.provisional" in summary.clinician_assessed
        # And none of them was asked of the patient.
        assert not any(
            slot.startswith("assessment.") for slot in summary.unanswered
        )


class TestAPainDescription:
    """The §13 worked example, run through the whole loop."""

    def test_one_sentence_yields_three_facts(self, agent: QuestioningAgent) -> None:
        state = run(
            agent,
            {
                "fixed.complaints": "pain",
                "fixed.chief_complaint": "pain",
                "fixed.timeline": "two weeks",
                "pain.description": (
                    "It's a burning pain on the right side of my stomach "
                    "and gets worse after eating."
                ),
            },
        )
        assert state.value("pain.character") == "burning"
        assert state.value("pain.site") == "upper_abdomen"
        assert "eating" in str(state.value("pain.aggravating"))


class TestSomebodyWhoDeniesThings:
    def test_a_denial_is_recorded_as_a_denial(self, agent: QuestioningAgent) -> None:
        """§16, end to end. The single most important thing not to get wrong."""
        state = run(
            agent,
            {
                "fixed.complaints": "respiratory",
                "fixed.chief_complaint": "respiratory",
                "fixed.timeline": "a week",
                "respiratory.wheeze": "no, no wheezing at all",
                "history.tobacco": "never",
            },
        )
        assert state.value("respiratory.wheeze") is False

    def test_an_unreadable_answer_earns_one_clarification_and_no_more(
        self, agent: QuestioningAgent
    ) -> None:
        """§19. Asked twice, then left alone — a patient asked three times has
        been told the app cannot understand them."""
        state = PatientState()
        for _ in range(3):
            turn = agent.next(state, language="en")
            assert turn is not None
            agent.answer(state, turn, "fever", language="en")

        asked: list[tuple[str, bool]] = []
        for _ in range(12):
            turn = agent.next(state, language="en")
            if turn is None:
                break
            asked.append((turn.id, turn.clarifying))
            agent.answer(state, turn, "hmm not sure really", language="en")

        clarified = [q for q, clarifying in asked if clarifying]
        assert clarified, "nothing was clarified"
        assert len(clarified) == len(set(clarified)), "something was clarified twice"

    def test_an_unread_answer_never_becomes_a_fact(
        self, agent: QuestioningAgent
    ) -> None:
        state = run(
            agent,
            {
                "fixed.complaints": "fever",
                "fixed.chief_complaint": "fever",
                "fixed.timeline": "a week",
                "fever.chills": "I think maybe, hard to say",
            },
        )
        # Hedged, so not certain — and never silently a yes.
        assert state.value("fever.chills") is not True or (
            state.known_facts["fever.chills"].certainty is Certainty.PROBABLE
        )

    def test_the_summary_says_what_could_not_be_read(
        self, agent: QuestioningAgent
    ) -> None:
        """Not an apology — a list of what to ask about in the room, which is
        the most useful thing an intake can hand over short of the answer."""
        state = run(
            agent,
            {
                "fixed.complaints": "fever",
                "fixed.chief_complaint": "fever",
                "fixed.timeline": "a week",
                "fever.measured": "qqqq",
            },
        )
        summary = agent.summarise(state)
        unreadable = {v.slot for v in summary.uncertain}
        assert "fever.measured" in unreadable
        assert any(v.evidence == "qqqq" for v in summary.uncertain)


class TestAnEmergency:
    def test_it_stops_and_says_so(self, agent: QuestioningAgent) -> None:
        state = run(
            agent,
            {
                "fixed.complaints": "bleeding",
                "fixed.chief_complaint": "bleeding",
                "fixed.timeline": "since this morning",
                "bleeding.site": "vomit",
                "bleeding.ongoing": "yes",
                "bleeding.amount": "large",
            },
        )
        assert state.stopped
        assert agent.next(state, language="en") is None

        summary = agent.summarise(state)
        assert summary.stopped_early
        assert "URGENT" in render(summary, agent.slots)

    def test_the_answers_given_before_it_stopped_are_still_in_the_case(
        self, agent: QuestioningAgent
    ) -> None:
        """Stopping the questionnaire does not throw away the intake."""
        state = run(
            agent,
            {
                "fixed.complaints": "bleeding",
                "fixed.chief_complaint": "bleeding",
                "fixed.timeline": "since this morning",
                "bleeding.site": "vomit",
                "bleeding.ongoing": "yes",
            },
        )
        assert state.value("bleeding.site") == "vomit"
        assert agent.summarise(state).sections


class TestInHindi:
    def test_a_whole_interview_in_hindi(self, agent: QuestioningAgent) -> None:
        state = run(
            agent,
            {
                "fixed.complaints": "बुखार",
                "fixed.chief_complaint": "fever",
                "fixed.timeline": "तीन दिन से",
                "fever.chills": "हाँ",
                "fever.measured": "नहीं",
            },
            language="hi",
        )
        assert state.active_domains == ("fever",)
        assert state.value("fever.duration")["value"] == 3
        assert state.value("fever.chills") is True
        assert state.value("fever.measured") is False
        # And the prerequisite closed, so the reading was never asked for.
        assert not state.knows("fever.maximum_temperature")


class TestDeterminism:
    def test_the_same_script_gives_the_same_case_twice(
        self, agent: QuestioningAgent
    ) -> None:
        """The acceptance criterion, checked on the whole loop rather than one
        selection."""
        first = run(agent, TestAFeverAndHeadache.SCRIPT)
        second = run(agent, TestAFeverAndHeadache.SCRIPT)
        assert first.known_facts == second.known_facts
        assert first.asked_questions == second.asked_questions
        assert render(agent.summarise(first), agent.slots) == render(
            agent.summarise(second), agent.slots
        )


class TestItWorksWithNoDiseaseModel:
    def test_the_engine_carries_no_disease_knowledge(
        self, agent: QuestioningAgent
    ) -> None:
        """§32, checked on what the engine actually holds.

        The registries are symptoms, information slots, questions and clinical
        priorities. There is no disease list to point at, no mapping from a
        symptom to a condition, and no classifier — and the interview above is
        the evidence that a good questionnaire does not need one.

        Checked against the loaded content rather than by grepping the source,
        because the source says "does not diagnose" in a dozen docstrings and a
        text search cannot tell a promise from a violation.
        """
        # Every slot belongs to a symptom area, the general history, the AYUSH
        # history, or the practitioner's own assessment. None of them is a
        # condition.
        domains = {slot.domain for slot in agent.slots.all}
        assert domains == {d.id for d in agent.slots.domains} | {
            "general",
            "ayush",
            "assessment",
        }

        # And nothing anywhere maps a finding to a disease.
        assert not hasattr(agent, "diseases")
        assert not hasattr(agent, "classifier")

    def test_a_full_case_is_produced_without_one(
        self, agent: QuestioningAgent
    ) -> None:
        summary = agent.summarise(run(agent, TestAFeverAndHeadache.SCRIPT))
        assert len(summary.sections) >= 3
        assert summary.chief_complaint == "fever"
