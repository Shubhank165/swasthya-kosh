"""Which questions could be asked right now — steps 4 to 7 of §10.

The `*` expansion happens here, and it is where question compression comes from.
A question extracting `*.onset` becomes, for a patient with fever, headache and
body ache, a question targeting three slots — so it scores three times the
coverage of any one of the specific onset questions and wins without the
selector knowing anything about merging.

**A question whose targets are all already known is dropped**, not scored zero.
The difference shows up on a cross-domain question where one of three domains
has been answered: it still has two slots to fill, so it stays, with its
coverage reduced to what is actually left.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.questioning_agent.core.patient_state import PatientState
from app.questioning_agent.core.schemas import Question
from app.questioning_agent.knowledge.information_schema import SlotRegistry
from app.questioning_agent.knowledge.questions import QuestionBank
from app.questioning_agent.questioning.dependencies import Tri, evaluate


@dataclass(frozen=True, slots=True)
class Candidate:
    """A question, and the slots it would actually fill for this patient."""

    question: Question
    #: Resolved against the active domains, and already filtered to the ones
    #: still unknown. Never empty — a candidate with nothing to fill is not one.
    targets: tuple[str, ...]

    @property
    def coverage(self) -> int:
        return len(self.targets)


def candidates(
    state: PatientState, bank: QuestionBank, slots: SlotRegistry
) -> tuple[Candidate, ...]:
    """Everything askable now, in bank order.

    Bank order rather than sorted: the selector sorts by score and breaks ties
    on question id, so the order here does not affect the outcome. It is stable
    for the sake of the tests and of anybody reading a decision log.
    """
    out: list[Candidate] = []
    for question in bank.adaptive:
        if state.was_asked(question.id):
            continue
        if question.domains and not set(question.domains) & set(state.active_domains):
            continue
        if evaluate(question.requires, state) is not Tri.YES:
            continue

        targets = _unknown_targets(question, state, slots)
        if not targets:
            continue
        out.append(Candidate(question=question, targets=targets))
    return tuple(out)


def _unknown_targets(
    question: Question, state: PatientState, slots: SlotRegistry
) -> tuple[str, ...]:
    """The slots this question would fill that are not filled already."""
    resolved: list[str] = []
    for target in question.extracts:
        if target.startswith("*."):
            resolved.extend(_expand(target, state, slots))
        else:
            resolved.append(target)

    return tuple(
        dict.fromkeys(
            target
            for target in resolved
            if not state.knows(target)
            # A slot the registry does not carry cannot be filled, and a
            # clinician-assessed one is not the engine's to ask about.
            and (slot := slots.get(target)) is not None
            and slot.patient_observable
        )
    )


def _expand(target: str, state: PatientState, slots: SlotRegistry) -> list[str]:
    """`*.onset` -> the onset slot of every active domain that has one.

    Domains that skip the slot are simply absent — `sleep` has no `pattern`, so
    a patient whose only complaint is sleep never sees the pattern question at
    all rather than seeing one that cannot be recorded.
    """
    local = target.split(".", 1)[1]
    return [
        f"{domain}.{local}"
        for domain in state.active_domains
        if f"{domain}.{local}" in slots
    ]


__all__ = ["Candidate", "candidates"]
