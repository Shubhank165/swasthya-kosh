"""Every touch choice must be answerable without reading it.

The kiosk serves patients who cannot read, so an option that arrives without an icon is a dead
end for them - the label alone carries no meaning. These tests fail if a new option is added
without one, which is the only way that stays true as the option set grows.
"""

from medikiosk.clinical.questions import ANSWER_UI, QUESTIONS, answer_ui
from medikiosk.kiosk.flow import KioskFlow, Stage
from medikiosk.models import PatientState


def test_language_and_who_screens_carry_icons() -> None:
    flow = KioskFlow()
    for option in flow.screen(PatientState())["options"]:
        assert option["icon"].startswith("lang_")

    flow.choose_language("hi")
    flow.set_abha(None)
    assert flow.stage is Stage.WHO
    icons = {option["icon"] for option in flow.screen(PatientState())["options"]}
    assert icons == {"person_one", "person_two"}


def test_every_interview_question_has_a_pictorial_answer_control() -> None:
    for question_id in QUESTIONS:
        assert answer_ui(question_id), f"{question_id} has no answer control"

    # The ones needing something richer than a tick and a cross are named explicitly.
    assert answer_ui("ask_complaint") == "body_map"
    assert answer_ui("ask_severity") == "faces"
    assert answer_ui("ask_duration") == "duration"
    # Anything not named falls back to yes/no, which is still pictorial.
    assert answer_ui("ask_fever") == "yes_no"
    assert set(ANSWER_UI) <= set(QUESTIONS), "ANSWER_UI names a question that does not exist"


