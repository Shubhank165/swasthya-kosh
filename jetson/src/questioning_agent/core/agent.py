"""The engine, as one object.

    agent = QuestioningAgent.load(Path("clinical/questioning"))
    state = PatientState()

    while (turn := agent.next(state, language="hi")) is not None:
        answer = ask_the_patient(turn)
        agent.answer(state, turn, answer, language="hi")

    case = agent.summarise(state)

**No I/O and no framework.** It reads content once at construction and after
that it is a function of the state you hand it: same state, same language, same
answer, same result, every time. That is what lets the end-to-end tests be
conversations rather than mocks, and it is what will let this run behind an
HTTP endpoint, inside the kiosk, or ported — see the offline note in
`docs/QUESTIONING_AGENT.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from questioning_agent.core.enums import AnswerType, Provenance
from questioning_agent.core.patient_state import PatientState
from questioning_agent.core.schemas import Question, QuestionDecision, ResponseRecord
from questioning_agent.interpretation import clarification
from questioning_agent.interpretation.interpreter import Interpreter
from questioning_agent.knowledge.information_schema import SlotRegistry
from questioning_agent.knowledge.questions import QuestionBank
from questioning_agent.localization.languages import Vocabularies
from questioning_agent.localization.localization_loader import Localization
from questioning_agent.output.case_summary import CaseSummary, build
from questioning_agent.questioning.question_selector import QuestionSelector
from questioning_agent.questioning.scoring import DEFAULT_WEIGHTS, Weights
from questioning_agent.safety.triage import TriageRules


@dataclass(frozen=True, slots=True)
class Turn:
    """One question, ready to put on a screen."""

    question: Question
    text: str
    #: `(option_id, label)`, already resolved for the runtime-filled question.
    options: tuple[tuple[str, str], ...]
    decision: QuestionDecision
    #: True when this is a re-ask of something unreadable rather than new.
    clarifying: bool = False

    @property
    def id(self) -> str:
        return self.question.id

    @property
    def answer_type(self) -> AnswerType:
        return self.question.answer_type


class QuestioningAgent:
    def __init__(
        self,
        slots: SlotRegistry,
        bank: QuestionBank,
        localization: Localization,
        vocabularies: Vocabularies,
        triage: TriageRules,
        weights: Weights = DEFAULT_WEIGHTS,
    ) -> None:
        self.slots = slots
        self.bank = bank
        self.localization = localization
        self.vocabularies = vocabularies
        self.triage = triage
        self._selector = QuestionSelector(bank, slots, weights)
        self._interpreter = Interpreter(slots, localization)
        self._pending: dict[int, clarification.Clarification] = {}

    @classmethod
    def load(cls, directory: Path, weights: Weights = DEFAULT_WEIGHTS) -> QuestioningAgent:
        slots = SlotRegistry.load(directory)
        return cls(
            slots=slots,
            bank=QuestionBank.load(directory, slots),
            localization=Localization.load(directory),
            vocabularies=Vocabularies.load(directory),
            triage=TriageRules.load(directory),
            weights=weights,
        )

    # --- the loop ------------------------------------------------------------

    def next(self, state: PatientState, *, language: str) -> Turn | None:
        """The next question, or `None` when there is nothing worth asking."""
        pending = self._pending.get(id(state))
        if pending is not None:
            return self._turn(
                pending.question,
                state,
                language,
                QuestionDecision(
                    question_id=pending.question.id,
                    score=0.0,
                    reasons=(f"the answer to {pending.slot} could not be read",),
                    targets=(pending.slot,),
                ),
                clarifying=True,
            )

        selection = self._selector.next(state)
        if selection is None:
            return None
        state.record_decision(selection.decision)
        return self._turn(selection.question, state, language, selection.decision)

    def answer(
        self, state: PatientState, turn: Turn, response: str, *, language: str
    ) -> ResponseRecord:
        """Take one answer, file what it yields, and run the safety check.

        The raw response is stored whatever the parser makes of it (§20), the
        routing answers set the active domains, and the triage rules run *after*
        the facts land — a rule about a value can only fire once the value is
        there.
        """
        vocabulary = self.vocabularies[language]
        record = self._interpreter.interpret(turn.question, response, state, vocabulary)

        pending = self._pending.pop(id(state), None)
        if pending is not None:
            record = record.model_copy(
                update={
                    "clarifying": True,
                    "facts": clarification.resolve(pending, record.facts),
                }
            )

        state.record_response(record)

        if turn.question.fixed_order is not None:
            self._apply_routing(state, turn.question, record)

        if pending is None:
            wanted = clarification.needed(turn.question, record.facts, state)
            if wanted is not None:
                state.record_clarification(turn.question.id)
                self._pending[id(state)] = wanted

        for flag in self.triage.check(state):
            state.raise_flag(flag)

        return record

    def skip(self, state: PatientState, turn: Turn) -> None:
        """The patient declined, or could not say.

        Recorded as asked so it does not come round again. Pressing somebody
        twice for something they have already refused is how an intake stops
        being finished at all.
        """
        state.record_skipped(turn.question.id)
        self._pending.pop(id(state), None)

    def summarise(self, state: PatientState) -> CaseSummary:
        return build(state, self.slots)

    # --- internals -----------------------------------------------------------

    def _turn(
        self,
        question: Question,
        state: PatientState,
        language: str,
        decision: QuestionDecision,
        *,
        clarifying: bool = False,
    ) -> Turn:
        options = self._option_ids(question, state)
        return Turn(
            question=question,
            text=self.localization.question_text(question.id, language),
            options=tuple(
                (option, self.localization.option_text(option, language))
                for option in options
            ),
            decision=decision,
            clarifying=clarifying,
        )

    def _option_ids(self, question: Question, state: PatientState) -> tuple[str, ...]:
        if question.options_from:
            value = state.value(question.options_from)
            if isinstance(value, (list, tuple)):
                return tuple(str(v) for v in value)
            return ()
        return question.options

    def _apply_routing(
        self, state: PatientState, question: Question, record: ResponseRecord
    ) -> None:
        """Turn the answers to the fixed questions into domains.

        This is the only place the engine writes state that is not a slot value,
        and it is why: `<domain>.present` is what every domain question's
        prerequisite reads, so ticking "fever" on question 1 has to become
        `fever.present = true` or nothing downstream is reachable.
        """
        for fact in record.facts:
            if fact.slot == "routing.complaints" and isinstance(fact.value, (list, tuple)):
                state.selected_complaints = [str(v) for v in fact.value]
                for domain in state.selected_complaints:
                    if f"{domain}.present" in self.slots:
                        state.note(
                            f"{domain}.present",
                            True,
                            provenance=Provenance.PATIENT_REPORTED,
                        )
            elif fact.slot == "routing.chief_complaint" and fact.value:
                state.chief_complaint = str(fact.value)


__all__ = ["QuestioningAgent", "Turn"]
