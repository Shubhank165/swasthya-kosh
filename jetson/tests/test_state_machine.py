from medikiosk.clinical.state_machine import ClinicalStateMachine
from medikiosk.models import PatientState


def test_first_question_asks_for_complaint() -> None:
    question = ClinicalStateMachine().next_question(PatientState())
    assert question is not None
    assert question.id == "ask_complaint"


def test_abdominal_path_requests_vomiting_after_common_fields() -> None:
    state = PatientState(complaint="abdominal pain", duration="3 days", severity=5)
    question = ClinicalStateMachine().next_question(state)
    assert question is not None
    assert question.id == "ask_vomiting"


def test_chest_path_requests_breathlessness_first() -> None:
    state = PatientState(complaint="chest pain", duration="today", severity=4)
    question = ClinicalStateMachine().next_question(state)
    assert question is not None
    assert question.id == "ask_breathlessness"
