"""The single source of truth for one intake.

Mutable, unlike everything else in this package, and deliberately: it is the one
thing that changes as the conversation runs, and threading a new copy through
every call would hide that rather than prevent it.

**Nothing else holds state.** The selector, the interpreter and the safety layer
are all functions of this object; give two of them the same state and they
behave identically, which is what "deterministic" means in practice and what
makes the end-to-end tests possible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from questioning_agent.core.enums import Certainty, Provenance
from questioning_agent.core.schemas import (
    ParsedFact,
    QuestionDecision,
    RedFlag,
    ResponseRecord,
)


@dataclass
class PatientState:
    """Everything known, everything asked, and everything said.

    The three collections that look similar are not:

    - `known_facts` — filled slots. What the case summary is built from.
    - `uncertain_facts` — the parser had a reading but not enough confidence.
      These are what clarification questions are made of, and they never become
      answers on their own.
    - `raw_responses` — what the patient typed or tapped, verbatim, whatever
      came of it.
    """

    #: Age, sex and anything else that gates a question without being a finding.
    patient_profile: dict[str, Any] = field(default_factory=dict)

    #: The problem areas chosen in fixed question 1. These *are* the active
    #: domains — every adaptive question hangs off one.
    selected_complaints: list[str] = field(default_factory=list)

    #: The one chosen in fixed question 2. Weights everything after it.
    chief_complaint: str | None = None

    known_facts: dict[str, ParsedFact] = field(default_factory=dict)
    uncertain_facts: dict[str, ParsedFact] = field(default_factory=dict)

    asked_questions: list[str] = field(default_factory=list)
    answered_questions: list[str] = field(default_factory=list)
    #: Questions the patient declined or could not answer. Asked, and not to be
    #: asked again — pressing somebody twice for something they have already
    #: refused is how an intake stops being completed at all.
    skipped_questions: list[str] = field(default_factory=list)

    raw_responses: list[ResponseRecord] = field(default_factory=list)
    clarification_history: list[str] = field(default_factory=list)
    decisions: list[QuestionDecision] = field(default_factory=list)

    #: Fired rules. Non-empty means the questionnaire stops.
    red_flags: list[RedFlag] = field(default_factory=list)

    # --- reading -------------------------------------------------------------

    @property
    def active_domains(self) -> tuple[str, ...]:
        """Domains in play, chief complaint first.

        Order matters to nothing that scores, but it makes the general
        questions and the case summary read in the order the patient thinks
        about their own problem.
        """
        ordered = list(self.selected_complaints)
        if self.chief_complaint and self.chief_complaint in ordered:
            ordered.remove(self.chief_complaint)
            ordered.insert(0, self.chief_complaint)
        return tuple(ordered)

    @property
    def stopped(self) -> bool:
        """True once a red flag has fired. Terminal — §28."""
        return bool(self.red_flags)

    def knows(self, slot: str) -> bool:
        return slot in self.known_facts

    def value(self, slot: str) -> Any:
        fact = self.known_facts.get(slot)
        return fact.value if fact else None

    def was_asked(self, question_id: str) -> bool:
        return question_id in self.asked_questions

    # --- writing -------------------------------------------------------------

    def record_asked(self, question_id: str) -> None:
        if question_id not in self.asked_questions:
            self.asked_questions.append(question_id)

    def record_skipped(self, question_id: str) -> None:
        self.record_asked(question_id)
        if question_id not in self.skipped_questions:
            self.skipped_questions.append(question_id)

    def record_response(self, record: ResponseRecord) -> None:
        """Take one answer: keep the words, file the facts.

        The raw response is stored first and unconditionally, so a parser that
        raises still leaves the sentence behind.
        """
        self.raw_responses.append(record)
        self.record_asked(record.question_id)
        if not record.clarifying and record.question_id not in self.answered_questions:
            self.answered_questions.append(record.question_id)
        for fact in record.facts:
            self.put(fact)

    def put(self, fact: ParsedFact) -> None:
        """File one fact, or file the doubt about it.

        **Certainty never rises here.** A slot already known is not overwritten
        by a less certain reading of a later sentence; the only thing that
        replaces a fact is a fact at least as certain, which in practice means
        the patient being asked again and answering plainly.
        """
        if not fact.usable:
            self.uncertain_facts[fact.slot] = fact
            return

        existing = self.known_facts.get(fact.slot)
        if existing is not None and _rank(existing.certainty) > _rank(fact.certainty):
            return

        self.known_facts[fact.slot] = fact
        # It is answered now, so there is nothing left to clarify.
        self.uncertain_facts.pop(fact.slot, None)

    def record_clarification(self, question_id: str) -> None:
        self.clarification_history.append(question_id)

    def record_decision(self, decision: QuestionDecision) -> None:
        self.decisions.append(decision)

    def raise_flag(self, flag: RedFlag) -> None:
        if not any(existing.id == flag.id for existing in self.red_flags):
            self.red_flags.append(flag)

    # --- convenience ---------------------------------------------------------

    def set_profile(self, key: str, value: Any) -> None:
        self.patient_profile[key] = value

    def note(self, slot: str, value: Any, *, provenance: Provenance) -> None:
        """File a value the engine itself established, not the patient.

        Used for the routing answers — which domains are active, which is the
        chief complaint — so they appear in the case summary alongside
        everything else instead of living only in two list attributes.
        """
        self.put(
            ParsedFact(
                slot=slot,
                value=value,
                certainty=Certainty.CERTAIN,
                provenance=provenance,
            )
        )


def _rank(certainty: Certainty) -> int:
    return {Certainty.CERTAIN: 2, Certainty.PROBABLE: 1, Certainty.UNCERTAIN: 0}[certainty]


__all__ = ["PatientState"]
