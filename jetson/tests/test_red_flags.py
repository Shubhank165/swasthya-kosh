import pytest

from medikiosk.clinical.heuristic import HeuristicClinicalExtractor
from medikiosk.clinical.red_flags import evaluate_red_flags
from medikiosk.models import PatientState, Urgency


def test_chest_pain_with_breathlessness_is_emergency() -> None:
    state = PatientState(complaint="chest pain", breathlessness=True)
    alerts = evaluate_red_flags(state)
    assert any(alert.rule_id == "RF_CHEST_PAIN_ASSOCIATED" for alert in alerts)
    assert any(alert.urgency == Urgency.EMERGENCY for alert in alerts)


def test_chest_pain_alone_does_not_trigger_combination_rule() -> None:
    state = PatientState(complaint="chest pain", breathlessness=False)
    alerts = evaluate_red_flags(state)
    assert not any(alert.rule_id == "RF_CHEST_PAIN_ASSOCIATED" for alert in alerts)


def test_possible_stroke_is_deterministic_emergency() -> None:
    alerts = evaluate_red_flags(PatientState(one_sided_weakness=True))
    assert alerts[0].rule_id == "RF_POSSIBLE_STROKE"
    assert alerts[0].urgency == Urgency.EMERGENCY


def test_severe_abdominal_pain_with_vomiting_is_urgent() -> None:
    state = PatientState(complaint="abdominal pain", severity=9, vomiting=True)
    alerts = evaluate_red_flags(state)
    assert any(alert.rule_id == "RF_SEVERE_ABDOMINAL_PAIN_VOMITING" for alert in alerts)


# --------------------------------------------------------------- stroke wording, heuristic only
#
# These two fields each raise an EMERGENCY on their own, no questionnaire asks them, and with
# Ollama down the heuristic extractor is the whole of the kiosk's stroke detection. The lists
# used to be exact substrings, so "slurred speech" fired and "my speech is slurred" did not -
# the ordinary way of saying it matched nothing at all.


async def _flags(transcript: str):
    update = await HeuristicClinicalExtractor().extract(transcript)
    state = PatientState()
    state.apply(update, transcript, "en")
    return evaluate_red_flags(state)


@pytest.mark.parametrize(
    "transcript",
    [
        "my right side has gone weak and my speech is slurred",
        "my speech is slurred",
        "my left arm is weak",
        "I cannot move my right leg",
        "मेरी दाहिनी तरफ कमजोरी है",
        "one side weak",
        "slurred speech",
    ],
)
async def test_stroke_wording_raises_an_emergency_without_the_llm(transcript: str) -> None:
    alerts = await _flags(transcript)
    assert any(a.rule_id == "RF_POSSIBLE_STROKE" for a in alerts), transcript
    assert any(a.urgency is Urgency.EMERGENCY for a in alerts), transcript


@pytest.mark.parametrize(
    "transcript",
    [
        "I feel weak and tired",
        "I have a weak appetite",
        "I am weak after the fever",
        "no weakness anywhere",
        "I have been feeling weak for a week",
    ],
)
async def test_ordinary_weakness_is_not_a_stroke(transcript: str) -> None:
    """A false EMERGENCY is its own harm: it sends a fatigued patient to resus and teaches staff
    to distrust the alert. Bare "weak" is deliberately not enough - a side word must be near it."""

    alerts = await _flags(transcript)
    assert not any(a.rule_id == "RF_POSSIBLE_STROKE" for a in alerts), transcript
