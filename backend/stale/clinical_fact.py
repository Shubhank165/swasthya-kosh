"""`ClinicalFact` — the atomic unit of the record.

Immutable by construction. A correction does not edit a fact; it creates a new
one whose `supersedes` points at the old. The chain of revisions *is* the audit
trail, which is the part of this product a clinician has to be able to trust.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from app.domain.clinical.enums import (
    ANSWERED_STATUSES,
    Certainty,
    FactStatus,
    ReporterRole,
    Section,
    SourceType,
    Temporality,
    certainty_rank,
)
from app.domain.clinical.provenance import (
    ConceptRef,
    FactId,
    FactValue,
    SourceRef,
    render_value,
)


class CertaintyIncreaseError(ValueError):
    """Raised when a revision would claim more confidence than its predecessor.

    Guards invariant 4: `"maybe two weeks"` must never quietly become `"2 weeks"`.
    Only a human act — patient confirmation or physician verification — may raise
    certainty, and those go through the dedicated methods below.
    """


@dataclass(frozen=True, slots=True)
class ClinicalFact:
    """One observation about one concept, with everything needed to defend it."""

    fact_id: FactId
    concept: ConceptRef
    status: FactStatus
    certainty: Certainty
    temporality: Temporality
    source_type: SourceType
    source_ref: SourceRef
    confidence: float
    reported_by: ReporterRole
    recorded_at: datetime
    section: Section
    value: FactValue | None = None
    original_expression: str | None = None
    original_language: str | None = None
    patient_confirmed: bool = False
    physician_verified: bool = False
    supersedes: FactId | None = None
    #: Why this fact exists — a precondition id, a rule id, an extractor note.
    #: Never clinical text; safe to log.
    note: str | None = None
    qualifiers: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be within 0.0..1.0, got {self.confidence}")
        valueless = {FactStatus.NOT_ASKED, FactStatus.NOT_APPLICABLE}
        if self.status in valueless and self.value is not None:
            raise ValueError(f"a {self.status} fact must not carry a value")
        if self.status is FactStatus.ABSENT and self.value is not None:
            raise ValueError("an ABSENT fact must not carry a value; absence has no magnitude")
        # A derived fact may be physician-verified, but only through
        # `verified_by_physician`, which is the one path that records the actor.
        if (
            self.physician_verified
            and self.source_type is SourceType.DERIVED
            and not self.patient_confirmed
            and self.note is None
        ):
            raise ValueError(
                "physician-verified derived fact must record its verification note"
            )

    # --- queries ------------------------------------------------------------

    @property
    def is_answered(self) -> bool:
        """True when the question was actually put and settled."""
        return self.status in ANSWERED_STATUSES

    @property
    def is_asserted(self) -> bool:
        """True when the fact positively claims the concept is present."""
        return self.status is FactStatus.PRESENT

    def rendered_value(self) -> str | None:
        return render_value(self.value)

    def display(self) -> str:
        """Concept plus value, for the summary builder. Not for logs."""
        rendered = self.rendered_value()
        base = self.concept.display or self.concept.concept_id.replace("_", " ")
        if rendered is None:
            return base
        return f"{base}: {rendered}"

    # --- revision -----------------------------------------------------------

    def revise(
        self,
        *,
        new_fact_id: FactId,
        recorded_at: datetime,
        status: FactStatus | None = None,
        value: FactValue | None = None,
        certainty: Certainty | None = None,
        temporality: Temporality | None = None,
        source_type: SourceType | None = None,
        source_ref: SourceRef | None = None,
        confidence: float | None = None,
        reported_by: ReporterRole | None = None,
        original_expression: str | None = None,
        original_language: str | None = None,
        note: str | None = None,
        allow_certainty_increase: bool = False,
    ) -> ClinicalFact:
        """Produce the successor revision of this fact.

        Certainty may not increase unless `allow_certainty_increase` is set,
        which only the human-confirmation paths do.
        """
        next_certainty = certainty if certainty is not None else self.certainty
        if not allow_certainty_increase and certainty_rank(next_certainty) > certainty_rank(
            self.certainty
        ):
            raise CertaintyIncreaseError(
                f"cannot promote certainty {self.certainty} -> {next_certainty} "
                f"for concept {self.concept.concept_id} without human confirmation"
            )
        next_status = status if status is not None else self.status
        clears_value = next_status in {
            FactStatus.ABSENT,
            FactStatus.NOT_ASKED,
            FactStatus.NOT_APPLICABLE,
        }
        return replace(
            self,
            fact_id=new_fact_id,
            status=next_status,
            value=None if clears_value else (value if value is not None else self.value),
            certainty=next_certainty,
            temporality=temporality if temporality is not None else self.temporality,
            source_type=source_type if source_type is not None else self.source_type,
            source_ref=source_ref if source_ref is not None else self.source_ref,
            confidence=confidence if confidence is not None else self.confidence,
            reported_by=reported_by if reported_by is not None else self.reported_by,
            original_expression=(
                original_expression if original_expression is not None else self.original_expression
            ),
            original_language=(
                original_language if original_language is not None else self.original_language
            ),
            note=note if note is not None else self.note,
            recorded_at=recorded_at,
            supersedes=self.fact_id,
            # A revision is a fresh claim: prior human sign-off does not carry over.
            patient_confirmed=False,
            physician_verified=False,
        )

    def confirmed_by_patient(self, *, new_fact_id: FactId, recorded_at: datetime) -> ClinicalFact:
        """Patient re-affirmed this fact during the confirmation loop.

        This is the one legitimate way REPORTED becomes CONFIRMED. It does not
        set `physician_verified`: the two flags are independent and neither
        implies the other.
        """
        return replace(
            self,
            fact_id=new_fact_id,
            certainty=(
                Certainty.CONFIRMED
                if self.certainty is Certainty.REPORTED
                else self.certainty
            ),
            patient_confirmed=True,
            recorded_at=recorded_at,
            supersedes=self.fact_id,
        )

    def verified_by_physician(
        self, *, new_fact_id: FactId, recorded_at: datetime, physician_id: str
    ) -> ClinicalFact:
        """Physician signed this fact off. Records who, in `note`."""
        return replace(
            self,
            fact_id=new_fact_id,
            physician_verified=True,
            recorded_at=recorded_at,
            supersedes=self.fact_id,
            note=f"verified_by={physician_id}",
        )
