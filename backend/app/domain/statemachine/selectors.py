"""Plan construction and field selection.

The plan is the full ordered list of fields this particular intake owes,
assembled from the core intake content, the matched complaint pathway, the
red-flag screen, the review-of-systems groups the pathway declared and the
Ayurveda module. It is rebuilt from the state on every call, so it is a pure
function of the facts — there is no hidden cursor to get out of sync.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.domain.clinical.enums import (
    SECTION_ORDER,
    FactStatus,
    Section,
    SourceType,
)
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.clinical.provenance import CodedValue
from app.domain.ontology.pathway import Pathway, PathwayField, PathwayRegistry


class FieldOrigin(StrEnum):
    """Where a planned field came from. Surfaces in `selection_reason`."""

    CORE = "core"
    PATHWAY = "pathway"
    RED_FLAG_SCREEN = "red_flag_screen"
    REVIEW_OF_SYSTEMS = "review_of_systems"
    AYURVEDA = "ayurveda"


@dataclass(frozen=True, slots=True)
class PlannedField:
    """A field the intake owes, with the section it sits in and its provenance."""

    field: PathwayField
    section: Section
    origin: FieldOrigin
    source_pathway: str

    @property
    def concept(self) -> str:
        return self.field.concept

    @property
    def required(self) -> bool:
        return self.field.required


@dataclass(frozen=True, slots=True)
class ContentSet:
    """Every piece of clinical content the state machine reads.

    Held as pathway objects so all content — core intake, complaint pathways,
    red-flag screens, ROS groups, Ayurveda — obeys one schema and one loader.
    """

    core: Pathway
    complaint_pathways: PathwayRegistry
    red_flag_screens: PathwayRegistry
    review_of_systems: PathwayRegistry
    ayurveda: Pathway | None = None
    #: Concept id whose answer selects the complaint pathway.
    chief_complaint_concept: str = "chief_complaint"
    #: Red-flag screen used when no complaint-specific screen exists.
    default_red_flag_screen: str = "general"


def _sort_key(planned: PlannedField) -> tuple[int, int, str]:
    """Deterministic order: section, then declared priority, then concept id.

    Concept id is the final tiebreak so two fields at the same priority never
    swap places between runs — the evaluation harness depends on this.
    """
    return (SECTION_ORDER.index(planned.section), planned.field.priority, planned.field.concept)


def build_plan(state: PatientIntakeState, content: ContentSet) -> tuple[PlannedField, ...]:
    """The ordered list of fields this intake owes, given what is known so far.

    Sections beyond the chief complaint expand only once the complaint is known,
    because the complaint decides which pathway, screen and ROS groups apply.
    """
    planned: list[PlannedField] = [
        PlannedField(f, f.section, FieldOrigin.CORE, content.core.pathway_id)
        for f in content.core.fields
    ]

    pathway = active_pathway(state, content)
    if pathway is not None:
        planned.extend(
            PlannedField(f, f.section, FieldOrigin.PATHWAY, pathway.pathway_id)
            for f in pathway.fields
        )
        screen = content.red_flag_screens.get(pathway.pathway_id) or content.red_flag_screens.get(
            content.default_red_flag_screen
        )
        if screen is not None:
            planned.extend(
                PlannedField(
                    f, Section.RED_FLAG_SCREEN, FieldOrigin.RED_FLAG_SCREEN, screen.pathway_id
                )
                for f in screen.fields
            )
        for group in pathway.review_of_systems:
            ros = content.review_of_systems.get(group)
            if ros is None:
                continue
            planned.extend(
                PlannedField(
                    f, Section.REVIEW_OF_SYSTEMS, FieldOrigin.REVIEW_OF_SYSTEMS, ros.pathway_id
                )
                for f in ros.fields
            )

    if content.ayurveda is not None and state.ayurveda_enabled:
        planned.extend(
            PlannedField(f, Section.AYURVEDA, FieldOrigin.AYURVEDA, content.ayurveda.pathway_id)
            for f in content.ayurveda.fields
        )

    # Deduplicate by concept, keeping the first (most specific) occurrence, so a
    # complaint pathway that already asks about vomiting is not asked again by ROS.
    seen: set[str] = set()
    unique: list[PlannedField] = []
    for item in planned:
        if item.concept in seen:
            continue
        seen.add(item.concept)
        unique.append(item)
    return tuple(sorted(unique, key=_sort_key))


def active_pathway(state: PatientIntakeState, content: ContentSet) -> Pathway | None:
    """The complaint pathway in force, or None while the complaint is unknown.

    Prefers the pathway already pinned on the state so a mid-intake correction
    to the chief complaint is an explicit re-pin, not a silent plan swap.
    """
    if state.active_pathway is not None:
        return content.complaint_pathways.get(state.active_pathway)
    complaint = state.fact_for(content.chief_complaint_concept)
    if complaint is None or complaint.status is not FactStatus.PRESENT:
        return None
    # The complaint may be recorded either as a coded value ("abdominal_pain"
    # chosen from a list) or as the concept itself; both must resolve.
    value = complaint.value
    coded = value.code if isinstance(value, CodedValue) else None
    return content.complaint_pathways.match_or_fallback(coded or complaint.concept.concept_id)


#: Sources that are not the patient speaking today. A fact from one of these is
#: put back to the patient for confirmation rather than treated as answered.
_NEEDS_PATIENT_CONFIRMATION: frozenset[SourceType] = frozenset(
    {SourceType.PRIOR_RECORD, SourceType.DOCUMENT}
)


def needs_confirmation(state: PatientIntakeState, concept_id: str) -> bool:
    """True when a record- or document-sourced fact awaits the patient's word.

    Such a concept is not "answered" for asking purposes: we ask "our record
    shows X — is that still correct?" rather than an open question. A line an OCR
    pass read off a two-year-old discharge summary is exactly the kind of thing a
    patient needs the chance to correct.
    """
    fact = state.fact_for(concept_id)
    if fact is None:
        return False
    return fact.source_type in _NEEDS_PATIENT_CONFIRMATION and not fact.patient_confirmed


def is_owed(state: PatientIntakeState, planned: PlannedField) -> bool:
    """True when the field still needs asking."""
    concept = planned.concept
    if concept in state.declined:
        return False
    if needs_confirmation(state, concept):
        return True
    status = state.status_of(concept)
    return status not in (
        {FactStatus.PRESENT, FactStatus.ABSENT, FactStatus.UNKNOWN, FactStatus.NOT_APPLICABLE}
    )


def precondition_is_decidable(state: PatientIntakeState, planned: PlannedField) -> bool:
    """True when every concept the precondition reads has been settled.

    An undecided precondition is not a failing one. Pregnancy is gated on sex and
    age; at the start of an intake neither has been asked, so the gate evaluates
    false — and marking the field NOT_APPLICABLE there would permanently rule out
    a question for a patient who turns out to be a pregnant woman.

    "Not applicable" means we know it does not apply. Until the inputs are in, we
    do not know, and the field simply waits.
    """
    precondition = planned.field.precondition
    if precondition is None:
        return True
    return all(state.is_settled(concept) for concept in precondition.concepts())


def inapplicable_fields(
    state: PatientIntakeState, plan: Sequence[PlannedField]
) -> tuple[PlannedField, ...]:
    """Owed fields that are decidably not applicable.

    Recorded as NOT_APPLICABLE rather than left dangling, so coverage reports a
    real denominator and the report can say *why* a question was never put.
    """
    return tuple(
        p
        for p in plan
        if is_owed(state, p)
        and precondition_is_decidable(state, p)
        and not p.field.applies_to(state)
    )


def outstanding_required(
    state: PatientIntakeState, plan: Sequence[PlannedField]
) -> tuple[PlannedField, ...]:
    """Required, owed and currently applicable fields, in plan order."""
    return tuple(
        p for p in plan if p.required and is_owed(state, p) and p.field.applies_to(state)
    )


def outstanding_optional(
    state: PatientIntakeState, plan: Sequence[PlannedField]
) -> tuple[PlannedField, ...]:
    """Optional, owed and currently applicable fields, in plan order."""
    return tuple(
        p for p in plan if not p.required and is_owed(state, p) and p.field.applies_to(state)
    )


def answered_optional_count(state: PatientIntakeState, plan: Sequence[PlannedField]) -> int:
    """How many optional questions have already been put to this patient."""
    return sum(1 for p in plan if not p.required and state.is_answered(p.concept))
