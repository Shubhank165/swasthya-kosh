"""Asking again instead of guessing — §19.

    Patient:  "I think maybe."
    Agent:    "Sorry — do you have a fever at the moment?"

The rule is simple and the discipline is the whole point: **an answer the parser
could not read does not become an answer.** It becomes an uncertain fact, which
earns one clarification, and if the clarification is no clearer the slot stays
empty and the case says so.

One re-ask, not a loop. A patient asked the same thing three times has been told
the app does not understand them, and the third answer is not better than the
first — it is shorter and more annoyed.
"""

from __future__ import annotations

from dataclasses import dataclass

from questioning_agent.core.patient_state import PatientState
from questioning_agent.core.schemas import ParsedFact, Question


@dataclass(frozen=True, slots=True)
class Clarification:
    """A question worth putting again, and what was unclear about the answer."""

    question: Question
    slot: str
    #: What the patient said that could not be read. Shown back to them in some
    #: presentations — "you said 'I think maybe'" — which is often enough on its
    #: own for somebody to correct themselves.
    unread: str | None


def needed(
    question: Question, facts: tuple[ParsedFact, ...], state: PatientState
) -> Clarification | None:
    """Whether this answer earns a re-ask.

    Three conditions, all of them necessary:

    1. Something was unreadable.
    2. Nothing else in the same answer filled that slot — a sentence that
       answered two of three targets is a good answer, not a failed one.
    3. It has not already been clarified. §19 gets one attempt.
    """
    if question.id in state.clarification_history:
        return None

    readable = {fact.slot for fact in facts if fact.usable}
    for fact in facts:
        if fact.usable or fact.slot in readable:
            continue
        return Clarification(question=question, slot=fact.slot, unread=fact.evidence)
    return None


def resolve(
    clarification: Clarification, facts: tuple[ParsedFact, ...]
) -> tuple[ParsedFact, ...]:
    """What the second answer yields, narrowed to the slot that was unclear.

    Narrowed deliberately. A clarification asks about one thing; letting its
    answer fill other slots would let "no, I meant my head" rewrite the duration
    somebody had already given clearly.
    """
    return tuple(fact for fact in facts if fact.slot == clarification.slot)


__all__ = ["Clarification", "needed", "resolve"]
