"""`PatientIntakeState` — the intake aggregate.

Holds the append-only fact log plus session metadata, and exposes the queries
the state machine, coverage engine, red-flag evaluator and summary builder run
against. Facts are only ever added through `apply`, which enforces supersession.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from app.domain.clinical.enums import (
    ANSWERED_STATUSES,
    FactStatus,
    IntakeState,
    ReporterRole,
    Section,
    SourceType,
)
from app.domain.clinical.fact import ClinicalFact
from app.domain.clinical.provenance import FactId, IntakeId, PatientId


class SupersessionError(ValueError):
    """Raised when an applied fact's supersession chain is inconsistent."""


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """A document attached to the intake, and how far processing got."""

    document_id: str
    kind: str  # prescription | lab_report | discharge_summary | other
    uploaded_at: datetime
    processed: bool = False
    page_count: int = 1
    low_confidence: bool = False


@dataclass(frozen=True, slots=True)
class PatientIntakeState:
    """Immutable aggregate. Every mutating method returns a new instance.

    `facts` is append-only and holds every revision ever recorded, oldest first.
    `current` resolves it to the live view: one fact per concept, superseded
    revisions removed.
    """

    intake_id: IntakeId
    facts: tuple[ClinicalFact, ...] = field(default_factory=tuple)
    state: IntakeState = IntakeState.NOT_STARTED
    revision: int = 0
    patient_id: PatientId | None = None
    language: str | None = None
    reporter: ReporterRole = ReporterRole.SELF
    #: Pathway id activated for the HPI section, once the chief complaint is known.
    active_pathway: str | None = None
    #: Review-of-systems groups the active pathway asked for.
    active_ros_groups: tuple[str, ...] = field(default_factory=tuple)
    ayurveda_enabled: bool = True
    documents: tuple[DocumentRecord, ...] = field(default_factory=tuple)
    #: Facts read off documents or prior records for a concept the patient has
    #: already answered. They are deliberately kept out of the live view — a scan
    #: must never overwrite what the patient said — but they stay on the record
    #: as the other half of a contradiction.
    record_facts: tuple[ClinicalFact, ...] = field(default_factory=tuple)
    #: Concepts the patient explicitly declined to answer. Distinct from UNKNOWN.
    declined: frozenset[str] = field(default_factory=frozenset)
    consent_artefact_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # --- fact log -----------------------------------------------------------

    def apply(self, fact: ClinicalFact) -> PatientIntakeState:
        """Append `fact`, enforcing supersession rules.

        A fact that supersedes must name a fact that exists and is currently
        live; a fact that does not supersede must not shadow a live fact for the
        same concept. Both violations are programming errors, not user errors.
        """
        current = self._current_map()
        live = current.get(fact.concept.concept_id)
        if fact.supersedes is not None:
            if fact.supersedes not in {f.fact_id for f in self.facts}:
                raise SupersessionError(
                    f"fact {fact.fact_id} supersedes unknown fact {fact.supersedes}"
                )
            if live is None or live.fact_id != fact.supersedes:
                raise SupersessionError(
                    f"fact {fact.fact_id} supersedes {fact.supersedes}, which is not the "
                    f"live revision for concept {fact.concept.concept_id}"
                )
        elif live is not None:
            raise SupersessionError(
                f"concept {fact.concept.concept_id} already has live fact {live.fact_id}; "
                "a replacement must supersede it"
            )
        return replace(self, facts=(*self.facts, fact), revision=self.revision + 1)

    def apply_record(self, fact: ClinicalFact) -> PatientIntakeState:
        """Apply a fact read off a document or a prior record.

        If the concept is untouched, the fact enters the live view — that is what
        lets the state machine ask "our record shows diabetes, is that still
        correct?" instead of asking cold. If the patient has already answered the
        concept, the fact is parked in `record_facts` instead: it is preserved as
        conflict evidence, and it does not displace what the patient said.
        """
        if self.fact_for(fact.concept.concept_id) is None:
            return self.apply(fact)
        return replace(
            self, record_facts=(*self.record_facts, fact), revision=self.revision + 1
        )

    def apply_all(self, facts: Iterable[ClinicalFact]) -> PatientIntakeState:
        """Apply facts in order. Later facts may supersede earlier ones in the
        same batch, which is what a multi-fact extraction from one utterance does."""
        state = self
        for fact in facts:
            state = state.apply(fact)
        return state

    def _current_map(self) -> dict[str, ClinicalFact]:
        superseded = {f.supersedes for f in self.facts if f.supersedes is not None}
        return {
            f.concept.concept_id: f for f in self.facts if f.fact_id not in superseded
        }

    # --- queries ------------------------------------------------------------

    def current(self) -> tuple[ClinicalFact, ...]:
        """Live facts, in the order they were first recorded."""
        return tuple(self._current_map().values())

    def fact_for(self, concept_id: str) -> ClinicalFact | None:
        """Live fact for `concept_id`, or None if the concept was never touched."""
        return self._current_map().get(concept_id)

    def by_id(self, fact_id: FactId) -> ClinicalFact | None:
        """Any revision, live or superseded, by id. Powers the evidence endpoint."""
        for fact in (*self.facts, *self.record_facts):
            if fact.fact_id == fact_id:
                return fact
        return None

    def all_facts(self) -> tuple[ClinicalFact, ...]:
        """Every fact on the record, live view and parallel record channel alike."""
        return (*self.facts, *self.record_facts)

    def history_of(self, concept_id: str) -> tuple[ClinicalFact, ...]:
        """Every revision recorded for a concept, oldest first."""
        return tuple(f for f in self.all_facts() if f.concept.concept_id == concept_id)

    def status_of(self, concept_id: str) -> FactStatus:
        """Status of a concept. A concept never touched is NOT_ASKED, not UNKNOWN."""
        fact = self.fact_for(concept_id)
        return FactStatus.NOT_ASKED if fact is None else fact.status

    def is_answered(self, concept_id: str) -> bool:
        """True when the concept has been put to the patient and settled."""
        return self.status_of(concept_id) in ANSWERED_STATUSES

    def is_settled(self, concept_id: str) -> bool:
        """True when nothing more is owed on the concept: answered, ruled out as
        not applicable, or explicitly declined."""
        if concept_id in self.declined:
            return True
        return self.status_of(concept_id) in (
            ANSWERED_STATUSES | {FactStatus.NOT_APPLICABLE}
        )

    def is_present(self, concept_id: str) -> bool:
        return self.status_of(concept_id) is FactStatus.PRESENT

    def facts_for(self, section: Section) -> tuple[ClinicalFact, ...]:
        """Live facts belonging to a section."""
        return tuple(f for f in self.current() if f.section is section)

    def facts_from(self, source_type: SourceType) -> tuple[ClinicalFact, ...]:
        return tuple(f for f in self.current() if f.source_type is source_type)

    def value_of(self, concept_id: str) -> str | None:
        fact = self.fact_for(concept_id)
        return None if fact is None else fact.rendered_value()

    def unverified_facts(self) -> tuple[ClinicalFact, ...]:
        """Live facts still awaiting a physician. AI- and document-derived facts
        start here and stay here until a physician acts."""
        return tuple(f for f in self.current() if not f.physician_verified)

    def sections_present(self) -> tuple[Section, ...]:
        seen = {f.section for f in self.current()}
        return tuple(s for s in Section if s in seen)

    def __iter__(self) -> Iterator[ClinicalFact]:
        return iter(self.current())

    def __len__(self) -> int:
        return len(self._current_map())

    # --- session metadata ---------------------------------------------------

    def with_state(self, state: IntakeState) -> PatientIntakeState:
        return replace(self, state=state, revision=self.revision + 1)

    def with_pathway(
        self, pathway_id: str, ros_groups: Sequence[str] = ()
    ) -> PatientIntakeState:
        return replace(
            self,
            active_pathway=pathway_id,
            active_ros_groups=tuple(ros_groups),
            revision=self.revision + 1,
        )

    def with_language(self, language: str) -> PatientIntakeState:
        return replace(self, language=language, revision=self.revision + 1)

    def with_reporter(self, reporter: ReporterRole) -> PatientIntakeState:
        return replace(self, reporter=reporter, revision=self.revision + 1)

    def with_patient(self, patient_id: PatientId) -> PatientIntakeState:
        return replace(self, patient_id=patient_id, revision=self.revision + 1)

    def with_consent(self, artefact_id: str) -> PatientIntakeState:
        return replace(self, consent_artefact_id=artefact_id, revision=self.revision + 1)

    def with_document(self, document: DocumentRecord) -> PatientIntakeState:
        remaining = tuple(d for d in self.documents if d.document_id != document.document_id)
        return replace(self, documents=(*remaining, document), revision=self.revision + 1)

    def with_declined(self, concept_id: str) -> PatientIntakeState:
        return replace(
            self, declined=self.declined | {concept_id}, revision=self.revision + 1
        )

    def with_ayurveda(self, enabled: bool) -> PatientIntakeState:
        return replace(self, ayurveda_enabled=enabled, revision=self.revision + 1)

    def with_timestamps(
        self, *, started_at: datetime | None = None, completed_at: datetime | None = None
    ) -> PatientIntakeState:
        return replace(
            self,
            started_at=started_at if started_at is not None else self.started_at,
            completed_at=completed_at if completed_at is not None else self.completed_at,
            revision=self.revision + 1,
        )

    def snapshot(self) -> Mapping[str, FactStatus]:
        """Concept -> status view, for diffing and for the evaluation harness."""
        return {cid: f.status for cid, f in self._current_map().items()}
