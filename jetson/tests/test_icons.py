"""Every touch choice must be answerable without reading it.

The kiosk serves patients who cannot read, so an option that arrives without an icon is a dead
end for them - the label alone carries no meaning. These tests fail if a new option is added
without one, which is the only way that stays true as the questionnaire grows.
"""

from medikiosk.clinical.questions import ANSWER_UI, QUESTIONS, answer_ui
from medikiosk.kiosk import ayurveda
from medikiosk.kiosk.flow import KioskFlow, Stage
from medikiosk.models import PatientState


def test_every_ayurveda_option_has_an_icon() -> None:
    for question in ayurveda.QUESTIONS:
        for option in question.options_for("hi"):
            assert option["icon"], f"{question.id}/{option['value']} has no icon"
            assert option["icon"] != "circle", f"{question.id}/{option['value']} kept the default"


def test_icons_are_distinct_within_a_question() -> None:
    """Two choices sharing a picture are indistinguishable to someone who cannot read them."""

    for question in ayurveda.QUESTIONS:
        icons = [option["icon"] for option in question.options_for("en")]
        assert len(icons) == len(set(icons)), f"{question.id} repeats an icon"


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


def test_dashavidha_is_translated_into_every_supported_language() -> None:
    """The questionnaire is mandatory, so it cannot silently fall back to English. A Tamil speaker
    reaching an English screen mid-intake has effectively been dropped out of the kiosk."""

    from medikiosk.languages import LANGUAGES

    for code in LANGUAGES:
        for question in ayurveda.QUESTIONS:
            assert code in question.text, f"{question.id} has no {code} question text"
            for option in question.options:
                assert code in option.label, f"{question.id}/{option.value} has no {code} label"


def test_translations_are_not_just_the_english_copied() -> None:
    """A missing translation that copies the English string would pass the coverage test above
    while still showing English to the patient."""

    non_latin = {"hi", "bn", "mr", "te", "ta", "gu", "kn", "pa"}
    for question in ayurveda.QUESTIONS:
        for code in non_latin:
            assert question.text[code] != question.text["en"], f"{question.id} {code} is English"
