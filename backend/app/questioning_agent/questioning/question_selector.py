"""The next question — §10.

    1. stopped?                     a fired red flag ends the interview
    2. an outstanding clarification? ask that before anything new
    3. the three fixed questions     in order, before anything adaptive
    4. candidates                    generate, filter, expand
    5. score
    6. best, or nothing

Step 6 is where the length of the interview comes from. There is no question
budget and no counter: the selector stops when nothing left to ask is worth the
asking, which is the score floor. That means the interview is short for a
patient with one simple problem and longer for one with four, which is the
behaviour you want and the behaviour a fixed budget cannot produce.

Ties break on question id. Not for elegance — so that the same state gives the
same question on two machines, which is what makes any of this testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.questioning_agent.core.patient_state import PatientState
from app.questioning_agent.core.schemas import Question, QuestionDecision
from app.questioning_agent.knowledge.information_schema import SlotRegistry
from app.questioning_agent.knowledge.questions import QuestionBank
from app.questioning_agent.questioning.candidate_generator import candidates
from app.questioning_agent.questioning.dependencies import Tri, evaluate
from app.questioning_agent.questioning.scoring import DEFAULT_WEIGHTS, Weights, score


@dataclass(frozen=True, slots=True)
class Selection:
    """What to ask, and why."""

    question: Question
    decision: QuestionDecision
    #: True when this is a re-ask of something the parser could not read, rather
    #: than a new question. The presentation layer says so; the engine needs to
    #: know because a clarification must not count as the question being asked
    #: for the first time.
    clarifying: bool = False


class QuestionSelector:
    def __init__(
        self,
        bank: QuestionBank,
        slots: SlotRegistry,
        weights: Weights = DEFAULT_WEIGHTS,
    ) -> None:
        self._bank = bank
        self._slots = slots
        self._weights = weights

    def next(self, state: PatientState) -> Selection | None:
        """The next question, or `None` when the interview is done."""
        if state.stopped:
            return None

        fixed = self._next_fixed(state)
        if fixed is not None:
            return fixed

        best: QuestionDecision | None = None
        for candidate in candidates(state, self._bank, self._slots):
            decision = score(candidate, state, self._slots, self._weights)
            if best is None or (decision.score, best.question_id) > (
                best.score,
                decision.question_id,
            ):
                best = decision

        if best is None or best.score < self._weights.floor:
            return None
        return Selection(question=self._bank.require(best.question_id), decision=best)

    def _next_fixed(self, state: PatientState) -> Selection | None:
        """The opening three, in order, before anything adaptive.

        Their preconditions are still evaluated: question 2 needs the answer to
        question 1, and asking "which of these is worst" before knowing what
        "these" are is a question with no options on it.
        """
        for question in self._bank.fixed:
            if state.was_asked(question.id):
                continue
            if evaluate(question.requires, state) is not Tri.YES:
                # Not yet knowable, which for the fixed three means the previous
                # one has not been answered. Nothing else may jump the queue.
                return None
            return Selection(
                question=question,
                decision=QuestionDecision(
                    question_id=question.id,
                    score=float("inf"),
                    reasons=(f"fixed opening question {question.fixed_order} of 3",),
                    targets=question.extracts,
                ),
            )
        return None


__all__ = ["QuestionSelector", "Selection"]
