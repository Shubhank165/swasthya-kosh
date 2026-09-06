"""The data the engine moves around.

Pydantic and frozen throughout, with `extra="forbid"`. A typo in a content file
is then a load error naming the file, rather than a field silently absent from
every case summary the hospital ever reads.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.questioning_agent.core.enums import (
    AnswerType,
    Certainty,
    DataType,
    Provenance,
)


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --- knowledge ---------------------------------------------------------------


class InformationSlot(Model):
    """One clinically useful thing to know.

    The unit the whole engine is built on. Questions are how slots get filled;
    what the practitioner needs is the slot.

    `priority` is 1-10 and is a clinical judgement about how much the answer
    changes what a practitioner does — not how interesting it is. It belongs in
    the content, reviewed, and it is on the review queue like everything else
    here.
    """

    id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    description: str = Field(min_length=1)
    data_type: DataType
    #: False for a slot the practitioner assesses. The engine never asks these
    #: and never fills them; they exist so the case has a place to put them.
    patient_observable: bool = True
    priority: int = Field(ge=1, le=10)
    #: Domains in which this slot is worth filling. Empty means every domain,
    #: which is how the general-history slots behave.
    applicable_domains: tuple[str, ...] = ()
    #: Asked of every patient regardless of what is wrong with them.
    required: bool = False
    allowed_values: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _codes_have_values(self) -> InformationSlot:
        if self.data_type in (DataType.CODE, DataType.CODE_SET) and not self.allowed_values:
            raise ValueError(f"slot {self.id!r} is a code with no allowed_values")
        return self


class Condition(Model):
    """When a question makes sense.

    Deliberately small. Four shapes cover every prerequisite in the bank, and a
    condition language with more in it is one nobody can read at review time.
    """

    #: The slot to look at.
    slot: str | None = None
    #: Satisfied when the slot equals this.
    equals: Any = None
    #: Satisfied when the slot's value is one of these.
    any_of: tuple[str, ...] = ()
    #: Satisfied when the slot has any value at all.
    known: bool | None = None
    #: Satisfied when this domain is active.
    domain_active: str | None = None
    #: All of these, or any of these. Mutually exclusive with the above.
    all: tuple[Condition, ...] = ()
    any: tuple[Condition, ...] = ()

    @model_validator(mode="after")
    def _one_shape(self) -> Condition:
        leaf = self.slot is not None or self.domain_active is not None
        branch = bool(self.all) or bool(self.any)
        if leaf and branch:
            raise ValueError("a condition is a leaf or a branch, never both")
        if not leaf and not branch:
            raise ValueError("a condition with nothing in it is always true; say so explicitly")
        return self


class Question(Model):
    """A way of finding out one or more slots.

    `extracts` may name several slots, and a `*` in place of the domain makes it
    a *general* question: `*.onset` fills the onset slot of every active domain
    at once. That is what stops a patient with fever, headache and body ache
    being asked when each of them started.
    """

    id: str = Field(min_length=1)
    answer_type: AnswerType
    extracts: tuple[str, ...] = Field(min_length=1)
    requires: Condition | None = None
    #: 1-10, and it is about the question rather than the slot: two questions
    #: filling the same slot can be worth different amounts depending on how
    #: reliably they do it.
    priority: int = Field(default=5, ge=1, le=10)
    #: What it costs the patient to answer. A multi-select of fifteen options is
    #: not the same ask as a yes/no, and the selector is allowed to know that.
    burden: int = Field(default=1, ge=1, le=5)
    #: Option ids, for the select types. Text for them lives in localization.
    options: tuple[str, ...] = ()
    #: A slot whose value supplies the options at runtime, instead of `options`.
    #:
    #: One question uses it: "which of these is worst" offers back what the
    #: patient just ticked. Re-offering all fifteen problem areas would be
    #: asking somebody to re-read a list they have only this moment finished
    #: reading, and offering a fixed subset would be guessing.
    options_from: str | None = None
    unit: str | None = None
    units: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    #: Fixed opening questions, asked in this order before anything adaptive.
    fixed_order: int | None = None
    #: Domains this question is only worth asking in. Empty means any.
    domains: tuple[str, ...] = ()

    @property
    def is_general(self) -> bool:
        """True when it fills the same slot across every active domain."""
        return any(slot.startswith("*.") for slot in self.extracts)

    @model_validator(mode="after")
    def _selects_have_options(self) -> Question:
        needs_options = {
            AnswerType.SINGLE_SELECT,
            AnswerType.MULTI_SELECT,
            AnswerType.BOOLEAN,
        }
        selects = needs_options - {AnswerType.BOOLEAN}
        if self.answer_type in selects and not (self.options or self.options_from):
            raise ValueError(
                f"question {self.id!r} is a select with neither `options` nor "
                f"`options_from`"
            )
        if self.options and self.options_from:
            raise ValueError(f"question {self.id!r} has both `options` and `options_from`")
        return self


# --- state -------------------------------------------------------------------


class Duration(Model):
    value: float
    unit: str = Field(min_length=1)
    #: True where the patient hedged — "about a week", "four or five days".
    approximate: bool = False


class ParsedFact(Model):
    """One slot, filled, with the words that filled it.

    `evidence` is the span of the patient's answer the parser matched on. It is
    what makes a wrong extraction findable afterwards, and it is why nothing in
    here throws the original text away.
    """

    slot: str = Field(min_length=1)
    value: Any = None
    certainty: Certainty = Certainty.CERTAIN
    provenance: Provenance = Provenance.PATIENT_REPORTED
    evidence: str | None = None

    @property
    def usable(self) -> bool:
        """Whether this may fill a slot.

        Uncertain facts are kept — they are what a clarification question is
        built from — but they do not become answers. Certainty never rises
        except by asking again.
        """
        return self.certainty is not Certainty.UNCERTAIN


class ResponseRecord(Model):
    """What the patient actually said, kept whatever the parser made of it.

    Never discarded and never summarised. A practitioner who doubts a
    structured value has to be able to read the sentence it came from.
    """

    question_id: str
    raw_response: str
    facts: tuple[ParsedFact, ...] = ()
    #: Set when the response was an answer to a clarification rather than to the
    #: question itself.
    clarifying: bool = False


class QuestionDecision(Model):
    """Why this question and not another one — §30."""

    question_id: str
    score: float
    reasons: tuple[str, ...] = ()
    #: The slots it is expected to fill, after `*` expansion.
    targets: tuple[str, ...] = ()


class RedFlag(Model):
    """A rule that stops the questionnaire.

    `label` is fixed wording that says a human must look now. It never names a
    condition, and it is never shown to the patient as a finding.
    """

    id: str
    severity: str
    label: str
    matched: tuple[str, ...] = ()


class CaseValue(Model):
    """One filled slot as the case summary presents it."""

    slot: str
    value: Any
    provenance: Provenance
    certainty: Certainty
    evidence: str | None = None


__all__ = [
    "CaseValue",
    "Condition",
    "Duration",
    "InformationSlot",
    "Model",
    "ParsedFact",
    "Question",
    "QuestionDecision",
    "RedFlag",
    "ResponseRecord",
    "date",
]
