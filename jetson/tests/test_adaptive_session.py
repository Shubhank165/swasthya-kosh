"""The adaptive questioning agent, wired in without weakening triage.

The agent chooses questions well. It also has no slot for one-sided weakness, speech difficulty,
altered consciousness or chest pain, and its own rules contain no stroke criterion at all. So the
thing worth testing is not that it asks good questions - its own 212 tests cover that - but that
switching to it did not quietly cost the kiosk the emergencies it used to catch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from medikiosk.clinical.adaptive import AdaptiveClinicalSession, load_agent
from medikiosk.clinical.heuristic import HeuristicClinicalExtractor
from medikiosk.clinical.hybrid import HybridClinicalExtractor
from medikiosk.models import Urgency

CONTENT = Path(__file__).resolve().parents[1] / "clinical" / "questioning"


class _Naturalizer:
    """The template naturalizer's contract, without importing the online one."""

    async def naturalize(self, question, state, language):  # noqa: ANN001, ANN201
        return question.template_for(language)


@pytest.fixture(scope="module")
def agent():
    return load_agent(CONTENT)


def session(agent) -> AdaptiveClinicalSession:
    return AdaptiveClinicalSession(
        agent, HybridClinicalExtractor(HeuristicClinicalExtractor(), None), "en"
    )


# ------------------------------------------------------------------ the safety property


async def test_a_stroke_still_raises_an_emergency(agent) -> None:
    """The agent has no stroke rule and no slot for weakness or speech.

    If the interview had been handed to it outright, this patient would have been asked about
    their cough and sent to a queue. The emergency comes from our own extractor and
    `red_flags.py`, which is why both still run on every transcript.
    """

    live = session(agent)
    result = await live.process_transcript(
        "my right side has gone weak and my speech is slurred", "en"
    )
    assert result.should_alert_staff is True
    assert any(alert.rule_id == "RF_POSSIBLE_STROKE" for alert in result.red_flags)
    assert any(alert.urgency is Urgency.EMERGENCY for alert in result.red_flags)


async def test_an_emergency_stops_the_agent_asking_anything_else(agent) -> None:
    live = session(agent)
    result = await live.process_transcript("I am bleeding heavily and cannot stop it", "en")
    assert result.should_alert_staff is True
    assert result.next_question_id is None, "no next question once staff are being called"


async def test_the_agents_own_rules_never_declare_an_emergency(agent) -> None:
    """Its rules are tuned for recall on different ground and are a second opinion, not a second
    authority. Two differently tuned things deciding one question is how a real alert gets lost."""

    live = session(agent)
    for text in [
        "there is blood in my stool",
        "sudden headache and my vision changed",
        "my pain is ten out of ten",
    ]:
        result = await live.process_transcript(text, "en")
        from_agent = [a for a in result.red_flags if a.rule_id.startswith("QA_")]
        assert all(a.urgency is not Urgency.EMERGENCY for a in from_agent)


async def test_agent_alerts_cannot_promote_a_turn_to_an_emergency(agent) -> None:
    """`should_alert_staff` is computed from our rules before the agent's are appended."""

    live = session(agent)
    result = await live.process_transcript("there is blood in my stool", "en")
    ours = [a for a in result.red_flags if not a.rule_id.startswith("QA_")]
    if not any(a.urgency is Urgency.EMERGENCY for a in ours):
        assert result.should_alert_staff is False


async def test_the_extractor_still_fills_our_state(agent) -> None:
    """Everything downstream - red flags, the differential, the report, the FHIR bundle - reads
    our PatientState. The agent fills its own and must not replace this."""

    live = session(agent)
    await live.process_transcript("I have had a fever for three days", "en")
    assert live.state.fever is True
    assert live.state.original_transcripts


# ------------------------------------------------------------------ the reason for the change


async def test_it_asks_different_questions_for_different_complaints(agent) -> None:
    """The whole point: derived from the answer, not read off a fixed list."""

    # Driven through the real answer path rather than the selector alone.
    fever = session(agent)
    for text in ["fever", "fever", "started three days ago"]:
        await fever.process_transcript(text, "en")
    cough = session(agent)
    for text in ["cough and breathing trouble", "cough", "two weeks, slowly worse"]:
        await cough.process_transcript(text, "en")

    fever_next = {fever.peek_question().id}
    cough_next = {cough.peek_question().id}
    for _ in range(10):
        f, c = fever.peek_question(skip=fever_next), cough.peek_question(skip=cough_next)
        if f:
            fever_next.add(f.id)
        if c:
            cough_next.add(c.id)
    assert fever_next != cough_next, "the two complaints produced the same question set"


# ------------------------------------------------------------------ robustness


async def test_an_unparseable_answer_does_not_loop_forever(agent) -> None:
    """A patient whose answer the agent cannot read must not be asked the same thing forever."""

    live = session(agent)
    seen: list[str] = []
    for _ in range(8):
        result = await live.process_transcript("asdfgh qwerty", "en", skip=seen)
        if result.next_question_id is None:
            break
        seen.append(result.next_question_id)
    assert len(seen) == len(set(seen)), f"repeated a question: {seen}"


async def test_an_empty_transcript_is_rejected(agent) -> None:
    live = session(agent)
    with pytest.raises(ValueError):
        await live.process_transcript("   ", "en")


async def test_it_offers_the_same_surface_as_the_fixed_session(agent) -> None:
    """`app.py` reaches for `.state`, `.state_machine.next_question(...)` and
    `.process_transcript(...)`. Losing any of them breaks the interview at runtime, not at
    import."""

    from medikiosk.clinical.heuristic import HeuristicClinicalExtractor as _H
    from medikiosk.clinical.state_machine import ClinicalStateMachine
    from medikiosk.session import ClinicalSession

    fixed = ClinicalSession(
        extractor=HybridClinicalExtractor(_H(), None),
        naturalizer=_Naturalizer(),
    )
    live = session(agent)
    for attribute in ("state", "state_machine", "process_transcript"):
        assert hasattr(live, attribute), f"adaptive session is missing {attribute}"
        assert hasattr(fixed, attribute), f"fixed session is missing {attribute}"
    assert isinstance(fixed.state_machine, ClinicalStateMachine)
    assert live.state_machine.next_question(live.state, ()) is not None


@pytest.mark.parametrize("language", ["en", "hi", "ta", "bn"])
async def test_questions_come_back_in_the_patients_language(agent, language: str) -> None:
    live = AdaptiveClinicalSession(
        agent, HybridClinicalExtractor(HeuristicClinicalExtractor(), None), language
    )
    question = live.peek_question()
    assert question is not None
    assert question.template_for(language).strip()
