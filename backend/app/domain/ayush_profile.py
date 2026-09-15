"""The AYUSH/Prakriti self-report, as the report reads it.

A patient-level profile, answered once and outliving any single visit — which
is why it is not a `ClinicalFactRecord` and has no `intake_id`. See
`AyushProfileRecord` for that argument in full.

`AyushProfileSnapshot` is frozen and reaches `builder.build()` as a finished
value, exactly as `TimelineSnapshot` and `DocumentExtraction` already do. The
builder performs no I/O to obtain it and never calls anything to produce it:
that is what keeps report output pure and byte-deterministic while the thing it
prints was read from a database somewhere upstream. `ReportService` does the
reading.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AyushAnswer(BaseModel):
    """One answered field of the module.

    `status` and `certainty` carry the same vocabularies `clinical_facts` uses.
    They are not re-declared as a narrower set here: a parallel vocabulary that
    happens to agree today is how decision 1 gets violated by accident, and the
    five statuses exist precisely so "asked and could not say" cannot silently
    become "not asked".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    field_id: str
    status: str
    certainty: str
    #: `None` for every status but `answered` — the same rule the fact table
    #: states for its own `value` column.
    value: dict[str, object] | list[object] | str | float | bool | None = None
    #: The patient's own words where they gave any, kept beside the normalised
    #: value for the reason decision 3 gives: the words travel with the fact.
    original_text: str | None = None


class AyushProfileSnapshot(BaseModel):
    """A profile as of one read. Frozen; the builder only ever prints it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answers: tuple[AyushAnswer, ...] = ()
    language: str = "en"
    #: The bundle version the answers were given against. A profile collected
    #: before the module changed was a different questionnaire, and a report
    #: that cannot say so is asserting more than it knows.
    content_version: str | None = None
    submitted_at: datetime | None = None

    @property
    def is_empty(self) -> bool:
        return not self.answers
