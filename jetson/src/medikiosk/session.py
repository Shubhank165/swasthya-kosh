import asyncio
from collections.abc import Container
from typing import Protocol

from medikiosk.clinical.answers import direct_answer
from medikiosk.clinical.red_flags import evaluate_red_flags
from medikiosk.clinical.state_machine import ClinicalStateMachine
from medikiosk.models import ClinicalUpdate, PatientState, QuestionSpec, TurnResult, Urgency


class Extractor(Protocol):
    async def extract(self, transcript: str) -> ClinicalUpdate: ...


class Naturalizer(Protocol):
    async def naturalize(
        self,
        question: QuestionSpec,
        state: PatientState,
        language: str | None,
    ) -> str: ...


class ClinicalSession:
    def __init__(self, extractor: Extractor, naturalizer: Naturalizer) -> None:
        self.extractor = extractor
        self.naturalizer = naturalizer
        self.state_machine = ClinicalStateMachine()
        self.state = PatientState()
        self._lock = asyncio.Lock()

    async def process_transcript(
        self,
        transcript: str,
        language: str | None,
        asked: QuestionSpec | None = None,
        skip: Container[str] = (),
    ) -> TurnResult:
        clean = " ".join(transcript.split()).strip()
        if not clean:
            raise ValueError("Transcript is empty")

        async with self._lock:
            update = await self.extractor.extract(clean)
            if asked is not None:
                # A bare "yes" only means something against the question that was asked, and it
                # never overrides a fact the extractor read out of the utterance itself.
                for field, value in direct_answer(asked, clean, language).items():
                    if getattr(update, field) is None:
                        setattr(update, field, value)
            self.state.apply(update, clean, language)
            alerts = evaluate_red_flags(self.state)
            emergency = any(alert.urgency == Urgency.EMERGENCY for alert in alerts)

            question_id: str | None = None
            wording: str | None = None
            if not emergency:
                # `skip` holds questions already asked without a usable answer. Without it the
                # turn advertises a question the caller has already given up on, and the
                # interview loops on it forever.
                question = self.state_machine.next_question(self.state, skip)
                if question is not None:
                    question_id = question.id
                    try:
                        wording = await self.naturalizer.naturalize(
                            question,
                            self.state,
                            language,
                        )
                    except Exception:
                        wording = question.template_for(language)

            return TurnResult(
                transcript=clean,
                language=language,
                state=self.state.model_copy(deep=True),
                red_flags=alerts,
                next_question_id=question_id,
                next_question=wording,
                should_alert_staff=emergency,
            )
