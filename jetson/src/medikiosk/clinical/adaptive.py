"""The adaptive questioning agent, wired in behind the interface `ClinicalSession` already has.

`ClinicalStateMachine` walks a fixed plan: ten questions, branched three ways on a keyword in the
complaint. It asks a patient with a two-day cough about chest pain radiation because the list says
so. The vendored `questioning_agent` picks each question from what is still unknown, so a fever
patient is asked about chills and a cough patient about wheeze, and neither is asked the other's
questions - about 26 questions instead of a fixed 70, and the difference is derived rather than
authored.

WHAT THIS MUST NOT CHANGE, and the reason this class exists rather than a straight swap:

`red_flags.py` is the only thing that declares an emergency, and it reads *our* `PatientState`.
Four of the fields it depends on - `altered_consciousness`, `one_sided_weakness`,
`speech_difficulty`, `chest_pain` - are never asked by any questionnaire, ours or the agent's.
They are filled only by `HybridClinicalExtractor` reading what the patient said in their own
words. The agent has no slot for any of them and its own rules cover different ground (blood in
stool, vision change with headache) while covering no stroke at all.

So a straight swap would have kept the interview running and silently stopped the kiosk detecting
strokes. Every transcript therefore still goes through our extractor into our `PatientState`, and
`evaluate_red_flags` still runs on it, exactly as before. The agent chooses what to ask next; it
does not decide what is an emergency, and it cannot suppress an alert.

The agent's own triage rules are read as well, but only ever as `staff_review` - they are a second
opinion about who needs looking at, not a second authority on emergencies.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Container
from pathlib import Path
from typing import Any

from medikiosk.clinical.red_flags import evaluate_red_flags
from medikiosk.models import PatientState, QuestionSpec, RedFlagAlert, TurnResult, Urgency

#: Languages the agent ships localization for. Anything else falls back to English inside it.
_TEMPLATE_LANGUAGE = "en"


def _short(language: str | None) -> str:
    normalized = (language or _TEMPLATE_LANGUAGE).lower()
    if normalized in {"hinglish", "hi-latn"}:
        normalized = "hi"
    return normalized[:2]


class _AgentQuestion:
    """A `questioning_agent` turn wearing the shape the rest of the kiosk expects.

    `app.py` reaches into `session.state_machine.next_question(...)` to re-ask an unanswered
    question, and renders whatever comes back through `QuestionSpec`. Rather than change every
    call site, the agent's turn is presented as one.
    """

    def __init__(self, turn: Any, language: str | None) -> None:
        self.turn = turn
        self.id = turn.id
        # Nothing in the agent maps onto one of our PatientState fields, and nothing should:
        # our fields are filled by the extractor. This exists because QuestionSpec has it.
        self.target_field = "complaint"
        self._text = turn.text
        self._language = _short(language)
        # True when the agent could not read the last answer and is asking again rather than
        # moving on. The patient has to be told, or the same question appearing twice reads as a
        # broken kiosk and they answer it the same unreadable way.
        self.clarifying = bool(getattr(turn, "clarifying", False))

    @property
    def options(self) -> tuple[tuple[str, str], ...]:
        return self.turn.options

    def template_for(self, language: str | None) -> str:
        return self._text

    def as_spec(self) -> QuestionSpec:
        return QuestionSpec(
            id=self.id,
            target_field=self.target_field,
            templates={_TEMPLATE_LANGUAGE: self._text, self._language: self._text},
        )


class _StateMachineAdapter:
    """Stands in for `ClinicalStateMachine` so `app.py` needs no change to re-ask a question."""

    def __init__(self, session: AdaptiveClinicalSession) -> None:
        self._session = session

    def next_question(
        self, state: PatientState, skip: Container[str] = ()
    ) -> _AgentQuestion | None:
        return self._session.peek_question(skip)


class AdaptiveClinicalSession:
    """Same surface as `ClinicalSession`: `.state`, `.state_machine`, `.process_transcript`."""

    def __init__(
        self,
        agent: Any,
        extractor: Any,
        language: str | None = None,
    ) -> None:
        from questioning_agent.core.patient_state import PatientState as AgentState

        self.agent = agent
        self.extractor = extractor
        self.state = PatientState()
        self.agent_state = AgentState()
        self.state_machine = _StateMachineAdapter(self)
        self.language = language
        self._lock = asyncio.Lock()
        self._pending: Any | None = None

    # ------------------------------------------------------------------ asking

    def peek_question(self, skip: Container[str] = ()) -> _AgentQuestion | None:
        """The next question the agent would ask, without consuming it.

        `skip` holds questions already put to the patient without a usable answer. They are
        skipped in the agent so it moves on instead of looping on one the patient cannot answer.
        """

        for question_id in skip:
            with_pending = self._pending
            if with_pending is not None and with_pending.id == question_id:
                self._pending = None
        for _ in range(len(skip) + 1):
            turn = self.agent.next(self.agent_state, language=_short(self.language))
            if turn is None:
                return None
            if turn.id not in skip:
                self._pending = turn
                return _AgentQuestion(turn, self.language)
            # Already asked and unanswered: tell the agent to stop offering it.
            self.agent.skip(self.agent_state, turn)
        return None

    # ------------------------------------------------------------------ answering

    async def process_transcript(
        self,
        transcript: str,
        language: str | None,
        asked: QuestionSpec | _AgentQuestion | None = None,
        skip: Container[str] = (),
    ) -> TurnResult:
        clean = " ".join(transcript.split()).strip()
        if not clean:
            raise ValueError("Transcript is empty")

        async with self._lock:
            if language:
                self.language = language

            # 1. Our extractor, unchanged. This is what keeps red flags working: the fields the
            #    stroke and consciousness rules read exist nowhere in the agent's schema.
            update = await self.extractor.extract(clean)
            self.state.apply(update, clean, language)

            # 2. The agent, for question selection only. A parse failure here must not lose the
            #    turn - the extractor has already recorded what the patient said.
            await asyncio.to_thread(self._feed_agent, clean, language)

            # 3. Our rules, unchanged and still the only authority on emergencies.
            alerts = evaluate_red_flags(self.state)
            emergency = any(alert.urgency is Urgency.EMERGENCY for alert in alerts)
            alerts = alerts + self._agent_review_alerts()

            question_id: str | None = None
            wording: str | None = None
            if not emergency:
                question = self.peek_question(skip)
                if question is not None:
                    question_id = question.id
                    wording = question.template_for(language)

            return TurnResult(
                transcript=clean,
                language=language,
                state=self.state,
                red_flags=alerts,
                next_question_id=question_id,
                next_question=wording,
                should_alert_staff=emergency,
            )

    def _feed_agent(self, transcript: str, language: str | None) -> None:
        """Hand the answer to the agent. Never raises: it selects questions, it does not record
        clinical facts, so a parse failure costs a better next question and nothing else."""

        turn = self._pending
        if turn is None:
            turn = self.agent.next(self.agent_state, language=_short(language or self.language))
        if turn is None:
            return
        try:
            self.agent.answer(
                self.agent_state, turn, transcript, language=_short(language or self.language)
            )
        except Exception:
            # An answer the agent cannot parse is skipped rather than re-asked forever.
            with contextlib.suppress(Exception):
                self.agent.skip(self.agent_state, turn)
        finally:
            self._pending = None

    def _agent_review_alerts(self) -> list[RedFlagAlert]:
        """The agent's own triage rules, as URGENT at most - never EMERGENCY.

        They cover ground ours does not (blood in stool, headache with vision change) and miss
        ground ours covers (stroke). Raising them to EMERGENCY would put a second, differently
        tuned authority in charge of the one decision that has to have exactly one - and
        `should_alert_staff` above is computed before these are added, so they cannot promote a
        turn to an emergency no matter what they contain.
        """

        try:
            fired = self.agent.triage.check(self.agent_state)
        except Exception:
            return []
        alerts = []
        for rule in fired or ():
            rule_id = getattr(rule, "id", None) or str(rule)
            alerts.append(
                RedFlagAlert(
                    rule_id=f"QA_{rule_id.upper()}",
                    urgency=Urgency.URGENT,
                    message="Questioning agent flagged this for a clinician to look at.",
                    evidence=[f"questioning_agent rule {rule_id}"],
                )
            )
        return alerts


def load_agent(content_root: Path) -> Any:
    """Load the vendored engine. Raises if the content is missing, so a misconfigured deploy
    fails at startup rather than halfway through a patient's interview."""

    from questioning_agent.core.agent import QuestioningAgent

    return QuestioningAgent.load(content_root)
