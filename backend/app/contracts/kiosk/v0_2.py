"""Kiosk input contract, schema_version 0.2.

**Additive over 0.1**, and that is the whole design. Every valid 0.1 payload is
a valid 0.2 payload with `schema_version` changed; 0.1 keeps its own contract,
its own normalizer and its own golden fixture, and devices running it keep
working. This is the first real exercise of the versioning procedure in 1/3
§4.2, and the cost of it is what that section promised: two new files and one
registry line.

What 0.2 adds is one field — `carried_forward` on a field outcome — and it adds
it because the record could not previously express something a physician needs:
that an answer came from a previous visit and whether the patient confirmed it
today. See `app.domain.record.CarriedForward` for why those are three different
claims rather than one.

The models it does not change are imported from 0.1 rather than copied. A
duplicated `KioskTurn` would drift, and the first symptom would be two versions
disagreeing about what a turn is.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contracts.kiosk.v0_1 import (
    KioskField,
    KioskIntakeV0_1,
    KioskPatientRef,
    KioskRedFlag,
    KioskTurn,
)

SCHEMA_VERSION = "0.2"

__all__ = [
    "SCHEMA_VERSION",
    "KioskCarriedForward",
    "KioskFieldV0_2",
    "KioskIntakeV0_2",
    "KioskPatientRef",
    "KioskRedFlag",
    "KioskTurn",
]


class KioskCarriedForward(BaseModel):
    """Where a carried-forward answer came from.

    `confirmed_today` has no default on purpose. A device that carried an answer
    forward and did not say whether it re-asked has told us nothing, and `None`
    records exactly that — whereas defaulting to `False` would assert the patient
    was asked and declined to confirm, which is a claim about a conversation
    that may never have happened.
    """

    model_config = ConfigDict(extra="allow")

    from_intake_id: str = Field(min_length=1)
    originally_recorded: date
    confirmed_today: bool | None = None


class KioskFieldV0_2(KioskField):  # noqa: N801 - the version *is* the name
    """A 0.1 field outcome, plus its carry-forward provenance."""

    carried_forward: KioskCarriedForward | None = None

    @model_validator(mode="after")
    def _carried_forward_needs_an_answer(self) -> Self:
        """A field with no answer cannot have carried one forward.

        `not_asked` with a carry-forward record is the contradiction worth
        catching: it would mean the device says both that it never put the
        question and that it brought an answer over from June. One of those is
        wrong, and guessing which would put a value on the record that nobody
        established.

        `unresolved` and `refused` are refused for the same reason. Only an
        `answered` field has something to have carried.
        """
        if self.carried_forward is not None and self.status != "answered":
            raise ValueError(
                f"a '{self.status}' field cannot carry an answer forward; "
                "there is no answer to carry"
            )
        return self


class KioskIntakeV0_2(KioskIntakeV0_1):  # noqa: N801 - the version *is* the name
    """The complete kiosk payload at schema_version 0.2."""

    schema_version: Literal["0.2"]  # type: ignore[assignment]
    fields: dict[str, KioskFieldV0_2] = Field(default_factory=dict)  # type: ignore[assignment]
