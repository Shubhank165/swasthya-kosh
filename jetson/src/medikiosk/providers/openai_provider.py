import json
from typing import Any

from openai import AsyncOpenAI

from medikiosk.clinical.questions import TemplateQuestionNaturalizer
from medikiosk.models import ClinicalUpdate, PatientState, QuestionSpec

__all__ = ["OpenAIClinicalExtractor", "OpenAIQuestionNaturalizer", "TemplateQuestionNaturalizer"]

EXTRACTION_INSTRUCTIONS = """
You extract explicitly stated clinical intake facts from one patient utterance.
Return only the supplied JSON schema. Do not diagnose, infer unstated facts, or convert
uncertainty into certainty. A denial such as "no vomiting" is false; absence of a mention
is null. Preserve the complaint in short neutral words. Severity is only a 0-10 number if
the speaker explicitly provides it. Evidence must contain short exact fragments from the
utterance supporting the extracted values. This is intake support, not medical advice.
""".strip()


class OpenAIClinicalExtractor:
    def __init__(self, api_key: str, model: str = "gpt-5.6-terra") -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def extract(self, transcript: str) -> ClinicalUpdate:
        response = await self.client.responses.create(
            model=self.model,
            reasoning={"effort": "low"},
            instructions=EXTRACTION_INSTRUCTIONS,
            input=transcript,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "clinical_update",
                    "schema": ClinicalUpdate.model_json_schema(),
                    "strict": True,
                },
                "verbosity": "low",
            },
            max_output_tokens=1200,
            store=False,
        )
        return ClinicalUpdate.model_validate_json(response.output_text)


class OpenAIQuestionNaturalizer:
    def __init__(self, api_key: str, model: str = "gpt-5.6-terra") -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def naturalize(
        self,
        question: QuestionSpec,
        state: PatientState,
        language: str | None,
    ) -> str:
        fallback = question.template_for(language)
        payload: dict[str, Any] = {
            "selected_question_id": question.id,
            "required_field": question.target_field,
            "target_language": language or "en-IN",
            "fallback_wording": fallback,
            "known_state": state.model_dump(
                mode="json",
                exclude={"original_transcripts", "updated_at"},
            ),
        }
        response = await self.client.responses.create(
            model=self.model,
            reasoning={"effort": "low"},
            instructions=(
                "Rewrite the selected intake question as one short, respectful, patient-friendly "
                "question in the requested language. Ask only for the required field. Do not add "
                "diagnosis, advice, reassurance, or extra questions. Return only the question."
            ),
            input=json.dumps(payload, ensure_ascii=False),
            text={"verbosity": "low"},
            max_output_tokens=120,
            store=False,
        )
        wording = response.output_text.strip()
        return wording or fallback


