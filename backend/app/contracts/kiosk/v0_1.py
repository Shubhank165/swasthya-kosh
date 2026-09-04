"""Kiosk input contract, schema_version 0.1.

Describes what arrives from the Jetson. **Provisional** — derived from what the
device currently produces, and expected to change. §4.2 is the procedure for
version 0.2, and the whole point of this file existing separately from
`app.domain.record` is that following that procedure costs three edits.

Permissive on purpose. This model's job is to decide *whether the payload can be
understood*, not to police it. Anything it rejects goes to the repair path
(§5.1) rather than being refused, because a rejected intake is a patient who
answered questions for seven minutes for nothing.

What it is strict about is the field-status vocabulary, because a status this
model silently coerced would be a certainty increase smuggled in at the door.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.1"


class KioskPatientRef(BaseModel):
    """How the kiosk identified the patient. Absent means guest."""

    model_config = ConfigDict(extra="allow")

    type: str = "guest"
    value: str | None = None


class KioskTurn(BaseModel):
    """One interview turn.

    Extra keys are allowed and kept: the Jetson emits acoustic telemetry (`rms`,
    VAD timings) that this build does not read but a later one might, and
    dropping it at the contract boundary would make it unrecoverable.
    """

    model_config = ConfigDict(extra="allow")

    turn_id: int
    question_id: str | None = None
    #: What the kiosk asked, in the interview language.
    asked_text: str | None = None
    #: What the patient said. Clinical text.
    transcript: str | None = None
    asr_confidence: float | None = None
    #: The field this turn was trying to fill.
    bound_field: str | None = None
    bound_value: Any = None
    resolved: bool | None = None
    language: str | None = None


class KioskField(BaseModel):
    """One field's outcome.

    `status` is required and is not defaulted. A payload that omits it has not
    told us whether the question was asked, and guessing would be exactly the
    silent certainty increase hard rule 2 forbids — so it fails the contract and
    goes to repair, where the model is instructed to mark it `unresolved`.
    """

    model_config = ConfigDict(extra="allow")

    status: Literal["answered", "unresolved", "not_asked", "not_applicable", "refused"]
    value: Any = None
    #: The patient's own words for this field.
    original_text: str | None = None
    language: str | None = None
    source_turn: int | None = None
    confidence: float | None = None
    unit: str | None = None
    #: Overrides the section this field is filed under, when the kiosk knows.
    section: str | None = None

    @model_validator(mode="after")
    def _valueless_statuses_carry_no_value(self) -> Self:
        if self.status != "answered" and self.value is not None:
            raise ValueError(
                f"a '{self.status}' field must not carry a value; "
                "an answer that was never bound has no value to carry"
            )
        return self


class KioskRedFlag(BaseModel):
    """A criterion that fired on the device. An event, not a rule to re-run."""

    model_config = ConfigDict(extra="allow")

    rule_id: str = Field(min_length=1)
    fired_at_turn: int | None = None
    criteria_met: list[str] = Field(default_factory=list)
    severity: str = "high"
    label: str | None = None


class KioskIntakeV0_1(BaseModel):  # noqa: N801 - the version *is* the name
    """The complete kiosk payload at schema_version 0.1."""

    model_config = ConfigDict(extra="allow")

    schema_version: Literal["0.1"]
    intake_id: str = Field(min_length=1)
    kiosk_id: str | None = None
    hospital_id: str = Field(min_length=1)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: Literal["complete", "partial", "aborted_red_flag", "abandoned"]
    language: str = "en"
    language_locked_at_turn: int | None = None
    reporter: str = "self"
    department_code: str | None = None
    patient_ref: KioskPatientRef = Field(default_factory=KioskPatientRef)
    turns: list[KioskTurn] = Field(default_factory=list)
    fields: dict[str, KioskField] = Field(default_factory=dict)
    red_flags: list[KioskRedFlag] = Field(default_factory=list)
    engine_version: str | None = None
    content_version: str | None = None
