from medikiosk.clinical.translations import QUESTION_TEXT
from medikiosk.models import PatientState, QuestionSpec

# Question id -> the PatientState field it fills. The state machine asks in a clinically ordered
# sequence; this table is only the binding between a question and its slot.
TARGET_FIELD: dict[str, str] = {
    "ask_complaint": "complaint",
    "ask_duration": "duration",
    "ask_severity": "severity",
    "ask_breathlessness": "breathlessness",
    "ask_radiation": "pain_radiation",
    "ask_sweating": "sweating",
    "ask_vomiting": "vomiting",
    "ask_fever": "fever",
    "ask_bleeding": "active_bleeding",
    "ask_age": "age_years",
}

# How a patient answers each question without reading it. The kiosk serves people who cannot
# read, so every interview question needs a pictorial way in: a body to tap, a row of faces, a
# sun and moon for time. Sent to the client with the question so the tablet, the browser and any
# future client all offer the same control for the same question.
ANSWER_UI: dict[str, str] = {
    "ask_complaint": "body_map",   # tap where it hurts
    "ask_duration": "duration",    # sun / moon / calendar bands
    "ask_severity": "faces",       # Wong-Baker style faces, 0-10
    "ask_age": "age_bands",        # child / adult / elder bands, then digits
}
DEFAULT_ANSWER_UI = "yes_no"       # a large green tick and a red cross


def answer_ui(question_id: str) -> str:
    return ANSWER_UI.get(question_id, DEFAULT_ANSWER_UI)


QUESTIONS: dict[str, QuestionSpec] = {
    question_id: QuestionSpec(
        id=question_id,
        target_field=field,
        templates=QUESTION_TEXT[question_id],
    )
    for question_id, field in TARGET_FIELD.items()
}


class TemplateQuestionNaturalizer:
    """Offline wording: the clinician-reviewed template, unchanged by any model."""

    async def naturalize(
        self,
        question: QuestionSpec,
        state: PatientState,
        language: str | None,
    ) -> str:
        del state
        return question.template_for(language)
