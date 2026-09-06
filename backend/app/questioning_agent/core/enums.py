"""The vocabularies the engine is built on.

Every one of these is closed. A string that is not in one of these enums is a
content error caught at load time, not a value that reaches a practitioner.
"""

from __future__ import annotations

from enum import StrEnum


class AnswerType(StrEnum):
    """How a question expects to be answered.

    **Not everything is a yes/no.** The single most common way to make an
    intake useless is to flatten "how long has this been going on" into a set of
    checkboxes, because the answer a patient would have given — "since about
    Tuesday, but worse since yesterday" — has nowhere to go.
    """

    BOOLEAN = "boolean"
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    NUMERIC = "numeric"
    DURATION = "duration"
    DATE = "date"
    FREE_TEXT = "free_text"
    #: Free text the interpreter is expected to pull several slots out of, such
    #: as a description of pain that carries character, site and triggers.
    STRUCTURED_TEXT = "structured_text"
    SCALE = "scale"


class DataType(StrEnum):
    """What a slot holds once it is filled."""

    BOOLEAN = "boolean"
    CODE = "code"
    CODE_SET = "code_set"
    NUMBER = "number"
    DURATION = "duration"
    DATE = "date"
    TEXT = "text"
    SCALE = "scale"


class Provenance(StrEnum):
    """Where a value came from, which the case summary must keep separate.

    The distinction is not bookkeeping. "The patient said three days" and "the
    system read three days out of a sentence" are different claims, and a
    practitioner reading the case has to be able to tell them apart before
    acting on one.
    """

    #: The patient chose an option or typed a value into the field for it.
    PATIENT_REPORTED = "patient_reported"
    #: The interpreter derived it from ordinary language. Still the patient's
    #: information, now with a parser between them and the record.
    SYSTEM_NORMALISED = "system_normalised"
    #: A slot the engine never asks. The practitioner fills these in.
    CLINICIAN_ASSESSED = "clinician_assessed"


class Certainty(StrEnum):
    """How sure the interpreter is, and what the engine may do about it.

    `UNCERTAIN` is a real state with a real consequence — it does not fill the
    slot and it earns a clarification question. The alternative is a number in a
    clinical record that nobody chose.
    """

    CERTAIN = "certain"
    PROBABLE = "probable"
    UNCERTAIN = "uncertain"


class Presence(StrEnum):
    """A symptom's state, and there are four of them, not two.

    Mirrors the five-status rule the rest of this project runs on: "not asked",
    "asked and denied" and "asked and could not say" are three different
    medico-legal positions and none of them is the others.
    """

    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"
    NOT_ASKED = "not_asked"
