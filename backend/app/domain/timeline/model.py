"""The medical timeline as a structure.

Deliberately **not** under `domain/report/`. That package is model-free by
design — `builder.py` is a template engine and nothing in it calls anything —
and a timeline is the one part of the report whose contents may have been
*selected* by a model. Keeping it in its own package is what stops the
distinction eroding: the report builder receives a finished `TimelineSnapshot`
as a value, the same way it already receives document extractions, and renders
every event through the same templates as every other line.

The word to hold onto is **selected**. An event names a date and a label that
already exist in a stored record. Nothing here authors prose, states a
diagnosis, or draws a conclusion; `validate.py` is what makes that a property
rather than a hope.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EventKind(StrEnum):
    """What kind of thing happened. Descriptive, never diagnostic."""

    #: A previous intake at this hospital.
    VISIT = "visit"
    #: Something read off an uploaded document.
    DOCUMENT = "document"
    #: A medicine recorded as started, stopped or continued.
    MEDICATION = "medication"
    #: A lab or imaging result with a date on it.
    INVESTIGATION = "investigation"


class TimelineSource(StrEnum):
    """How the event was chosen."""

    #: Pure code walked the stored records. No model involved.
    DETERMINISTIC = "deterministic"
    #: A model selected it from candidates and pure code then checked it.
    MODEL_SELECTED = "model_selected"


class TimelineStatus(StrEnum):
    """What the reader is looking at, which the report must always say.

    A filtered timeline that does not announce it is filtered looks like a
    complete history and is not — so this travels to the renderer rather than
    being inferred from whether the list is short.
    """

    #: Everything found, in date order, nothing judged for relevance.
    UNFILTERED = "unfiltered"
    #: A subset selected as related to today's complaint.
    FILTERED = "filtered"
    #: Not built yet. The report says so rather than showing an empty section.
    PENDING = "pending"


class ClinicalEvent(BaseModel):
    """One dated thing that happened, with the record it came from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: **Required.** An undated event cannot go on a timeline, and inventing a
    #: date to place one is the single worst thing this feature could do.
    event_date: date
    kind: EventKind
    #: At most twelve words, copied or minimally shortened from the source.
    label: str
    source: TimelineSource = TimelineSource.DETERMINISTIC
    #: The intake this came from, for click-through and for the date check.
    intake_id: str | None = None
    document_id: str | None = None
    #: The short id the model was given (`c1`..`cN`). Kept so an event can be
    #: matched back to the candidate it claims to be, which is how a
    #: hallucinated one is caught.
    candidate_id: str | None = None
    #: 0..1. Always 1.0 for a deterministic event — pure code did not guess.
    relevance: float = 1.0
    #: Why it was selected, naming the shared element. Never a conclusion.
    relevance_reason: str | None = None


class TimelineSnapshot(BaseModel):
    """A built timeline, handed to the report builder as a plain value.

    Frozen, and the builder does no I/O to obtain it — exactly how
    `DocumentExtraction` already reaches `build()`. That is what keeps the
    report pure and byte-deterministic while its contents may have been chosen
    by a model somewhere upstream.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: TimelineStatus = TimelineStatus.PENDING
    events: tuple[ClinicalEvent, ...] = ()
    #: How many candidates were judged unrelated and left out. Printed, because
    #: "3 earlier events are not shown" is the difference between a filtered
    #: history and a short one.
    omitted_count: int = 0
    provider: str | None = None
    model_id: str | None = None
    generated_at: datetime | None = None

    @property
    def is_empty(self) -> bool:
        return not self.events

    @classmethod
    def pending(cls) -> TimelineSnapshot:
        return cls(status=TimelineStatus.PENDING)


class TimelineCandidate(BaseModel):
    """One prior record offered for selection, under a short opaque id.

    `candidate_id` is `c1`..`cN` rather than a uuid so a model returns something
    short and checkable, and so nothing identifying travels in the id itself.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    event_date: date
    kind: EventKind
    label: str
    intake_id: str | None = None
    document_id: str | None = None
    #: Coded values from the record, for the model to judge relatedness on.
    tags: tuple[str, ...] = ()


class TimelineRequest(BaseModel):
    """What a provider is asked to select from.

    Everything here has been through `redact()`. There is no name, no phone, no
    ABHA address and no MRN; the candidate ids are opaque.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Today's coded complaint, plus today's answered voice facts. Not free
    #: text from a red flag, and nothing out of `ingest_raw`.
    today: dict[str, str] = Field(default_factory=dict)
    candidates: tuple[TimelineCandidate, ...] = ()
    language: str = "en"
    max_events: int = 12


class TimelineDraft(BaseModel):
    """What a provider returns. Proposals, not findings.

    Every one goes through `validate.py` before it can reach a report: an
    unknown `candidate_id` is dropped, a date that contradicts its candidate is
    dropped, and anything below the relevance floor is dropped. The model
    proposes; pure code disposes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    events: tuple[ClinicalEvent, ...] = ()
    #: A model's own count of what it left out. Advisory — the real figure is
    #: computed after validation, because a model that drops an event and does
    #: not say so would otherwise understate the gap.
    omitted_count: int = 0
