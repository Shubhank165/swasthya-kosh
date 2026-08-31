"""Contradiction detection.

Compares what the patient says today against prior records and what was read off
their documents. When the two disagree it says so and stops. It never picks a
winner: deciding which of two conflicting histories is true is a clinical act,
and the entire value of surfacing the conflict is destroyed if software silently
resolves it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.domain.clinical.enums import FactStatus, SourceType
from app.domain.clinical.fact import ClinicalFact
from app.domain.clinical.patient_state import PatientIntakeState


class ConflictKind(StrEnum):
    """What sort of disagreement this is. Drives how the report words it."""

    STATUS = "status"  # one says present, the other absent
    VALUE = "value"  # both present, different values (dose, date, site)
    PRESENCE_ONLY_IN_RECORD = "presence_only_in_record"  # record has it, patient did not mention


#: Source types that represent "what we already held about this patient", as
#: opposed to what they told us during this intake.
_RECORD_SOURCES: frozenset[SourceType] = frozenset(
    {SourceType.PRIOR_RECORD, SourceType.DOCUMENT}
)

#: Source types that represent the patient speaking now.
_TODAY_SOURCES: frozenset[SourceType] = frozenset(
    {SourceType.VOICE, SourceType.TOUCH, SourceType.STAFF}
)

#: Concept families where a conflict is clinically material. Everything else is
#: noise: nobody needs an alert because a pain score moved from 6 to 7.
DEFAULT_WATCHED_PREFIXES: tuple[str, ...] = (
    "condition_",
    "allergy_",
    "medication_",
    "surgery_",
    "diagnosis_",
)

#: Individual concepts always watched regardless of prefix.
DEFAULT_WATCHED_CONCEPTS: frozenset[str] = frozenset(
    {
        "known_diabetes",
        "known_hypertension",
        "known_thyroid_disorder",
        "known_asthma",
        "drug_allergy",
        "current_medications",
        "past_surgery",
        "pregnancy",
    }
)


@dataclass(frozen=True, slots=True)
class ConflictSide:
    """One half of a conflict, with everything needed to display its provenance."""

    fact_id: str
    statement: str
    source_type: SourceType
    source_label: str
    confidence: float
    recorded_at_label: str
    patient_confirmed: bool

    @classmethod
    def of(cls, fact: ClinicalFact) -> ConflictSide:
        return cls(
            fact_id=str(fact.fact_id),
            statement=_statement_of(fact),
            source_type=fact.source_type,
            source_label=_source_label(fact),
            confidence=fact.confidence,
            recorded_at_label=fact.recorded_at.strftime("%H:%M"),
            patient_confirmed=fact.patient_confirmed,
        )


@dataclass(frozen=True, slots=True)
class Contradiction:
    """A disagreement between two facts about the same concept. Never resolved."""

    concept: str
    kind: ConflictKind
    reported_today: ConflictSide | None
    from_record: ConflictSide
    #: Always the same demand. Software's job here ends at "a human must look".
    resolution: str = "Physician verification required"

    def render(self) -> str:
        """The block the physician report prints. Deliberately symmetrical: it
        gives both sides equal visual weight so neither reads as the correct one."""
        lines = ["INFORMATION CONFLICT"]
        if self.reported_today is not None:
            lines.append(
                f"  Patient today   : {self.reported_today.statement:<32} "
                f"[{self.reported_today.source_label}, "
                f"{self.reported_today.recorded_at_label}"
                f"{', confirmed' if self.reported_today.patient_confirmed else ''}]"
            )
        else:
            lines.append(f"  Patient today   : {'not mentioned':<32} [-]")
        lines.append(
            f"  Prior record    : {self.from_record.statement:<32} "
            f"[{self.from_record.source_label}, conf {self.from_record.confidence:.2f}]"
        )
        lines.append(f"  → {self.resolution}")
        return "\n".join(lines)

    def fact_ids(self) -> tuple[str, ...]:
        ids = [self.from_record.fact_id]
        if self.reported_today is not None:
            ids.insert(0, self.reported_today.fact_id)
        return tuple(ids)


def _source_label(fact: ClinicalFact) -> str:
    """Short provenance label, e.g. `voice` or `Discharge_summary_2.jpg p1`."""
    ref = fact.source_ref
    if ref.document is not None:
        return f"{ref.document.document_id} p{ref.document.page}"
    if ref.transcript is not None:
        return f"{fact.source_type.value} @{ref.transcript.start_ms}ms"
    return fact.source_type.value


def _statement_of(fact: ClinicalFact) -> str:
    """How this fact reads in a conflict block."""
    label = fact.concept.display or fact.concept.concept_id.replace("_", " ")
    rendered = fact.rendered_value()
    if fact.status is FactStatus.ABSENT:
        return f"denies {label}"
    if fact.status is FactStatus.UNKNOWN:
        return f"unsure about {label}"
    if rendered is not None:
        return f"{label}: {rendered}"
    return label


def is_watched(concept_id: str, *, prefixes: Sequence[str], concepts: frozenset[str]) -> bool:
    """True when a conflict on this concept is worth a physician's attention."""
    return concept_id in concepts or any(concept_id.startswith(p) for p in prefixes)


def _conflicting(today: ClinicalFact, record: ClinicalFact) -> ConflictKind | None:
    """The kind of conflict between two facts, or None if they agree.

    UNKNOWN never conflicts: a patient who cannot remember has not contradicted
    anything, and flagging that would bury the real conflicts in noise.
    """
    if FactStatus.UNKNOWN in {today.status, record.status}:
        return None
    if today.status is not record.status:
        if {today.status, record.status} == {FactStatus.PRESENT, FactStatus.ABSENT}:
            return ConflictKind.STATUS
        return None
    if today.status is FactStatus.PRESENT:
        today_value = today.rendered_value()
        record_value = record.rendered_value()
        if today_value is not None and record_value is not None and today_value != record_value:
            return ConflictKind.VALUE
    return None


def detect(
    state: PatientIntakeState,
    *,
    watched_prefixes: Sequence[str] = DEFAULT_WATCHED_PREFIXES,
    watched_concepts: frozenset[str] = DEFAULT_WATCHED_CONCEPTS,
    report_unmentioned: bool = True,
) -> tuple[Contradiction, ...]:
    """Every material disagreement in `state`, in concept order.

    Both sides are read from the fact log rather than the live view, because the
    live view keeps only one fact per concept and a conflict needs both.
    """
    everything = state.all_facts()
    superseded = {f.supersedes for f in everything if f.supersedes is not None}
    live = [f for f in everything if f.fact_id not in superseded]

    today_by_concept: dict[str, ClinicalFact] = {}
    record_by_concept: dict[str, list[ClinicalFact]] = {}
    for fact in live:
        concept_id = fact.concept.concept_id
        if not is_watched(concept_id, prefixes=watched_prefixes, concepts=watched_concepts):
            continue
        if fact.source_type in _TODAY_SOURCES:
            today_by_concept[concept_id] = fact
        elif fact.source_type in _RECORD_SOURCES:
            record_by_concept.setdefault(concept_id, []).append(fact)

    found: list[Contradiction] = []
    for concept_id in sorted(record_by_concept):
        today = today_by_concept.get(concept_id)
        for record in record_by_concept[concept_id]:
            if today is None:
                if report_unmentioned and record.status is FactStatus.PRESENT:
                    found.append(
                        Contradiction(
                            concept=concept_id,
                            kind=ConflictKind.PRESENCE_ONLY_IN_RECORD,
                            reported_today=None,
                            from_record=ConflictSide.of(record),
                        )
                    )
                continue
            kind = _conflicting(today, record)
            if kind is not None:
                found.append(
                    Contradiction(
                        concept=concept_id,
                        kind=kind,
                        reported_today=ConflictSide.of(today),
                        from_record=ConflictSide.of(record),
                    )
                )
    return tuple(found)
