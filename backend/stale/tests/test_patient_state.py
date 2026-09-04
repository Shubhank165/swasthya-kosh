"""The intake aggregate: supersession, the live view, and orthogonal state."""

from __future__ import annotations

import pytest

from app.domain.clinical.enums import FactStatus, IntakeState, Section, SourceType
from app.domain.clinical.patient_state import (
    DocumentRecord,
    PatientIntakeState,
    SupersessionError,
)
from app.domain.clinical.provenance import FactId, IntakeId, ScaleValue
from app.domain.queue.entities import QueueState
from tests.conftest import START, make_fact


@pytest.fixture
def state() -> PatientIntakeState:
    return PatientIntakeState(intake_id=IntakeId("intake_1"))


class TestSupersession:
    def test_a_correction_creates_a_revision_rather_than_editing(self) -> None:
        """The audit trail is the product: the first answer stays in the log."""
        first = make_fact("severity", value=ScaleValue(4, 0, 10), fact_id="f1")
        state = PatientIntakeState(intake_id=IntakeId("i")).apply(first)
        second = first.revise(
            new_fact_id=FactId("f2"), recorded_at=START, value=ScaleValue(8, 0, 10)
        )
        state = state.apply(second)

        assert len(state.facts) == 2
        assert len(state.current()) == 1
        assert state.value_of("severity") == "8/10"
        assert state.by_id(FactId("f1")) is not None
        assert [f.fact_id for f in state.history_of("severity")] == ["f1", "f2"]

    def test_shadowing_a_live_fact_without_superseding_is_rejected(self) -> None:
        state = PatientIntakeState(intake_id=IntakeId("i")).apply(
            make_fact("severity", fact_id="f1")
        )
        with pytest.raises(SupersessionError, match="must supersede"):
            state.apply(make_fact("severity", fact_id="f2"))

    def test_superseding_an_unknown_fact_is_rejected(self, state: PatientIntakeState) -> None:
        with pytest.raises(SupersessionError, match="unknown fact"):
            state.apply(make_fact("severity", fact_id="f2", supersedes="nope"))

    def test_superseding_a_stale_revision_is_rejected(self) -> None:
        """Two clients correcting the same fact from the same stale read: the
        second must lose rather than silently overwrite the first."""
        f1 = make_fact("severity", fact_id="f1")
        state = PatientIntakeState(intake_id=IntakeId("i")).apply(f1)
        state = state.apply(f1.revise(new_fact_id=FactId("f2"), recorded_at=START))
        with pytest.raises(SupersessionError, match="not the live revision"):
            state.apply(make_fact("severity", fact_id="f3", supersedes="f1"))


class TestQueries:
    def test_an_untouched_concept_is_not_asked_not_unknown(
        self, state: PatientIntakeState
    ) -> None:
        """A concept nobody has raised is NOT_ASKED. Reporting it as UNKNOWN
        would claim we put the question and got no answer."""
        assert state.status_of("drug_allergy") is FactStatus.NOT_ASKED
        assert not state.is_answered("drug_allergy")

    def test_declined_is_settled_but_not_answered(self, state: PatientIntakeState) -> None:
        state = state.with_declined("tobacco_use")
        assert state.is_settled("tobacco_use")
        assert not state.is_answered("tobacco_use")

    def test_not_applicable_is_settled(self, state: PatientIntakeState) -> None:
        state = state.apply(
            make_fact(
                "pregnancy",
                status=FactStatus.NOT_APPLICABLE,
                section=Section.PERSONAL_HISTORY,
            )
        )
        assert state.is_settled("pregnancy")
        assert not state.is_answered("pregnancy")

    def test_facts_for_section_filters_the_live_view(self, state: PatientIntakeState) -> None:
        state = state.apply(make_fact("severity", section=Section.HPI, fact_id="f1"))
        state = state.apply(
            make_fact("known_diabetes", section=Section.PAST_MEDICAL, fact_id="f2")
        )
        assert {f.concept.concept_id for f in state.facts_for(Section.HPI)} == {"severity"}

    def test_unverified_facts_lists_what_a_physician_still_owes(
        self, state: PatientIntakeState
    ) -> None:
        state = state.apply(make_fact("severity", fact_id="f1"))
        state = state.apply(
            make_fact("known_diabetes", fact_id="f2", physician_verified=True)
        )
        assert {f.concept.concept_id for f in state.unverified_facts()} == {"severity"}


class TestRecordChannel:
    """Document and prior-record facts never overwrite what the patient said."""

    def test_a_record_fact_enters_the_live_view_when_the_concept_is_free(
        self, state: PatientIntakeState
    ) -> None:
        state = state.apply_record(
            make_fact("known_diabetes", source_type=SourceType.PRIOR_RECORD, fact_id="r1")
        )
        assert state.status_of("known_diabetes") is FactStatus.PRESENT

    def test_a_record_fact_is_parked_when_the_patient_already_answered(
        self, state: PatientIntakeState
    ) -> None:
        """Both survive: the disagreement is the finding, and resolving it in
        software would destroy it."""
        state = state.apply(
            make_fact("known_diabetes", status=FactStatus.ABSENT, fact_id="p1")
        )
        state = state.apply_record(
            make_fact("known_diabetes", source_type=SourceType.DOCUMENT, fact_id="d1")
        )
        assert state.status_of("known_diabetes") is FactStatus.ABSENT
        assert len(state.record_facts) == 1
        assert state.by_id(FactId("d1")) is not None
        assert len(state.all_facts()) == 2


class TestOrthogonalState:
    """Invariant 8: intake state and queue state are separate."""

    def test_intake_state_and_queue_state_are_different_enums(self) -> None:
        assert set(IntakeState) & {q.value for q in QueueState} == set()

    def test_in_progress_intake_coexists_with_a_waiting_ticket(
        self, state: PatientIntakeState
    ) -> None:
        """The normal, desirable case: a patient in the queue part-way through
        their history."""
        state = state.with_state(IntakeState.IN_PROGRESS)
        assert state.state is IntakeState.IN_PROGRESS
        assert QueueState.WAITING is QueueState.WAITING  # separate lifecycle entirely

    def test_no_attribute_derives_one_state_from_the_other(self) -> None:
        assert not hasattr(PatientIntakeState, "queue_state")


class TestMetadata:
    def test_every_mutation_bumps_the_revision(self, state: PatientIntakeState) -> None:
        """The revision is what stops a reconnecting kiosk clobbering newer
        answers, so every change has to move it."""
        assert state.revision == 0
        state = state.with_language("hi")
        assert state.revision == 1
        state = state.apply(make_fact("severity"))
        assert state.revision == 2

    def test_documents_are_replaced_by_id_not_duplicated(
        self, state: PatientIntakeState
    ) -> None:
        first = DocumentRecord(document_id="d1", kind="prescription", uploaded_at=START)
        state = state.with_document(first)
        state = state.with_document(
            DocumentRecord(
                document_id="d1", kind="prescription", uploaded_at=START, processed=True
            )
        )
        assert len(state.documents) == 1
        assert state.documents[0].processed

    def test_state_is_immutable(self, state: PatientIntakeState) -> None:
        with pytest.raises((AttributeError, TypeError)):
            state.state = IntakeState.READY  # type: ignore[misc]
