"""Coverage, contradictions and the summary builder."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.content import ClinicalContent
from app.domain.clinical.enums import (
    Certainty,
    FactStatus,
    ReporterRole,
    Section,
    SourceType,
)
from app.domain.clinical.patient_state import DocumentRecord, PatientIntakeState
from app.domain.clinical.provenance import (
    CodedValue,
    Duration,
    IntakeId,
    ScaleValue,
    TextValue,
)
from app.domain.contradictions.detector import ConflictKind, detect
from app.domain.coverage.coverage import compute
from app.domain.statemachine.engine import ClinicalStateMachine
from app.domain.summary.builder import build
from app.domain.summary.templates import find_unsupported_assertions
from tests.conftest import make_fact

NOW = datetime(2026, 1, 15, 11, 4, tzinfo=UTC)


@pytest.fixture
def state() -> PatientIntakeState:
    return PatientIntakeState(intake_id=IntakeId("i1")).with_pathway("fever", ("respiratory",))


class TestCoverage:
    def test_an_empty_intake_reports_zero_and_lists_its_gaps(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        """"92%" alone is useless to a doctor; the list of missing fields is
        what they act on."""
        report = compute(state, machine.plan(state))
        assert report.percentage == 0.0
        assert not report.is_complete
        missing = report.missing_required()
        assert missing
        assert all(m.reason == "not_asked" for m in missing)
        assert any("allergy" in m.describe() for m in missing)

    def test_not_applicable_shrinks_the_denominator_rather_than_counting_as_a_gap(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        """A male patient's pregnancy question is a real outcome, not a hole."""
        base = compute(state, machine.plan(state))
        with_na = state.apply(
            make_fact(
                "pregnancy",
                status=FactStatus.NOT_APPLICABLE,
                section=Section.PERSONAL_HISTORY,
                fact_id="na1",
            )
        )
        after = compute(with_na, machine.plan(with_na))
        assert after.required_not_applicable == 1
        assert after.denominator == base.denominator - 1
        assert not any(m.concept == "pregnancy" for m in after.missing_required())

    def test_unknown_counts_as_captured(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        """"I don't know" is a captured answer. Counting it as a gap would send
        the kiosk round in circles."""
        state = state.apply(
            make_fact(
                "known_diabetes",
                status=FactStatus.UNKNOWN,
                section=Section.PAST_MEDICAL,
                fact_id="f1",
            )
        )
        report = compute(state, machine.plan(state))
        assert report.required_captured == 1

    def test_a_declined_field_counts_towards_completion(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        state = state.with_declined("tobacco_use")
        report = compute(state, machine.plan(state))
        assert report.required_declined == 1
        assert not any(m.concept == "tobacco_use" for m in report.missing_required())

    def test_a_section_with_nothing_to_ask_is_complete_not_zero(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        report = compute(state, machine.plan(state))
        for section in report.sections:
            if section.denominator == 0:
                assert section.percentage == 100.0

    def test_missing_fields_are_ordered_required_first(
        self, machine: ClinicalStateMachine, state: PatientIntakeState
    ) -> None:
        missing = compute(state, machine.plan(state)).missing()
        required_flags = [m.required for m in missing]
        assert required_flags == sorted(required_flags, reverse=True)


class TestContradictions:
    def _with_conflict(self) -> PatientIntakeState:
        state = PatientIntakeState(intake_id=IntakeId("i1"))
        state = state.apply(
            make_fact(
                "known_diabetes",
                status=FactStatus.ABSENT,
                section=Section.PAST_MEDICAL,
                source_type=SourceType.VOICE,
                fact_id="today1",
                recorded_at=NOW,
                display="Diabetes",
                patient_confirmed=True,
            )
        )
        return state.apply_record(
            make_fact(
                "known_diabetes",
                status=FactStatus.PRESENT,
                value=TextValue("Type 2 Diabetes Mellitus"),
                section=Section.PAST_MEDICAL,
                source_type=SourceType.DOCUMENT,
                confidence=0.94,
                fact_id="doc1",
                recorded_at=NOW,
                display="Diabetes",
            )
        )

    def test_a_denial_against_a_document_is_reported(self) -> None:
        conflicts = detect(self._with_conflict())
        assert len(conflicts) == 1
        assert conflicts[0].kind is ConflictKind.STATUS
        assert conflicts[0].concept == "known_diabetes"

    def test_the_conflict_is_never_resolved(self) -> None:
        """Deciding which history is true is a clinical act. Software resolving
        it silently destroys the entire value of surfacing it."""
        conflict = detect(self._with_conflict())[0]
        assert conflict.resolution == "Physician verification required"
        assert conflict.reported_today is not None
        assert conflict.from_record is not None

    def test_both_sides_carry_their_provenance(self) -> None:
        conflict = detect(self._with_conflict())[0]
        assert conflict.reported_today.source_type is SourceType.VOICE
        assert conflict.from_record.source_type is SourceType.DOCUMENT
        assert conflict.from_record.confidence == 0.94
        assert "Discharge_summary_2.jpg" in conflict.from_record.source_label

    def test_the_rendered_block_matches_the_brief_s_shape(self) -> None:
        rendered = detect(self._with_conflict())[0].render()
        assert "INFORMATION CONFLICT" in rendered
        assert "Patient today" in rendered
        assert "Prior record" in rendered
        assert "denies Diabetes" in rendered
        assert "Physician verification required" in rendered
        assert "conf 0.94" in rendered

    def test_unknown_never_conflicts(self) -> None:
        """A patient who cannot remember has not contradicted anything, and
        flagging it would bury the real conflicts in noise."""
        state = PatientIntakeState(intake_id=IntakeId("i1"))
        state = state.apply(
            make_fact(
                "known_diabetes",
                status=FactStatus.UNKNOWN,
                section=Section.PAST_MEDICAL,
                fact_id="t1",
            )
        )
        state = state.apply_record(
            make_fact(
                "known_diabetes",
                status=FactStatus.PRESENT,
                section=Section.PAST_MEDICAL,
                source_type=SourceType.DOCUMENT,
                fact_id="d1",
            )
        )
        assert detect(state) == ()

    def test_a_record_condition_never_mentioned_today_is_surfaced(self) -> None:
        state = PatientIntakeState(intake_id=IntakeId("i1")).apply_record(
            make_fact(
                "known_hypertension",
                status=FactStatus.PRESENT,
                section=Section.PAST_MEDICAL,
                source_type=SourceType.PRIOR_RECORD,
                fact_id="r1",
            )
        )
        conflicts = detect(state)
        assert conflicts[0].kind is ConflictKind.PRESENCE_ONLY_IN_RECORD
        assert conflicts[0].reported_today is None

    def test_a_dose_change_is_a_value_conflict(self) -> None:
        state = PatientIntakeState(intake_id=IntakeId("i1"))
        state = state.apply(
            make_fact(
                "current_medications",
                value=TextValue("metformin 1000mg"),
                section=Section.MEDICATIONS,
                fact_id="t1",
            )
        )
        state = state.apply_record(
            make_fact(
                "current_medications",
                value=TextValue("metformin 500mg"),
                section=Section.MEDICATIONS,
                source_type=SourceType.DOCUMENT,
                fact_id="d1",
            )
        )
        assert detect(state)[0].kind is ConflictKind.VALUE

    def test_immaterial_concepts_are_not_flagged(self) -> None:
        """Nobody needs an alert because a pain score moved from 6 to 7."""
        state = PatientIntakeState(intake_id=IntakeId("i1"))
        state = state.apply(make_fact("severity", value=ScaleValue(7, 0, 10), fact_id="t1"))
        state = state.apply_record(
            make_fact(
                "severity",
                value=ScaleValue(6, 0, 10),
                source_type=SourceType.DOCUMENT,
                fact_id="d1",
            )
        )
        assert detect(state) == ()


class TestSummaryBuilder:
    def _populated(self) -> PatientIntakeState:
        state = PatientIntakeState(intake_id=IntakeId("i1")).with_pathway("fever", ("respiratory",))
        facts = [
            make_fact(
                "chief_complaint",
                value=CodedValue(code="fever", display="Fever"),
                section=Section.CHIEF_COMPLAINT,
                original_expression="bukhar aur khansi",
                original_language="hi",
                display="Chief complaint",
                fact_id="f1",
            ),
            make_fact(
                "duration",
                value=Duration(3, "days"),
                section=Section.HPI,
                certainty=Certainty.APPROXIMATE,
                original_expression="lagbhag teen din",
                original_language="hi",
                display="Duration",
                fact_id="f2",
            ),
            make_fact(
                "cough",
                section=Section.HPI,
                display="Cough",
                reported_by=ReporterRole.FAMILY_ATTENDANT,
                fact_id="f3",
            ),
            make_fact(
                "drug_allergy",
                status=FactStatus.ABSENT,
                section=Section.ALLERGIES,
                display="Drug allergy",
                fact_id="f4",
            ),
            make_fact(
                "known_diabetes",
                status=FactStatus.UNKNOWN,
                section=Section.PAST_MEDICAL,
                display="Diabetes",
                fact_id="f5",
            ),
        ]
        for fact in facts:
            state = state.apply(fact)
        return state

    def test_every_line_carries_the_facts_it_was_built_from(
        self, machine: ClinicalStateMachine
    ) -> None:
        """This is what turns a statement into evidence the physician can click."""
        state = self._populated()
        summary = build(state, coverage=compute(state, machine.plan(state)))
        lines = [line for section in summary.sections for line in section.lines]
        assert lines
        for line in lines:
            assert line.fact_ids
            assert state.by_id(line.fact_ids[0]) is not None

    def test_the_verbatim_expression_appears_beside_the_normalised_value(
        self, machine: ClinicalStateMachine
    ) -> None:
        state = self._populated()
        text = build(state, coverage=compute(state, machine.plan(state))).render_text()
        assert "bukhar aur khansi" in text
        assert "lagbhag teen din" in text

    def test_approximate_and_attendant_reported_facts_are_marked(
        self, machine: ClinicalStateMachine
    ) -> None:
        """A physician reading "3 days" needs to know at a glance that the
        patient hedged, and that the cough was the attendant's word."""
        state = self._populated()
        text = build(state, coverage=compute(state, machine.plan(state))).render_text()
        assert "approximate" in text
        assert "reported by attendant" in text

    def test_denials_and_unknowns_render_distinctly(
        self, machine: ClinicalStateMachine
    ) -> None:
        state = self._populated()
        text = build(state, coverage=compute(state, machine.plan(state))).render_text()
        assert "Denies Drug allergy" in text
        assert "Diabetes: patient unsure" in text

    def test_unestablished_fields_print_under_unresolved_rather_than_vanishing(
        self, machine: ClinicalStateMachine
    ) -> None:
        """The difference between "no allergies" and "we never got to allergies"
        is one a physician has to be able to see."""
        state = self._populated()
        summary = build(state, coverage=compute(state, machine.plan(state)))
        text = summary.render_text()
        assert "UNRESOLVED" in text
        assert summary.unresolved

    def test_a_declined_concept_is_named_in_unresolved(
        self, machine: ClinicalStateMachine
    ) -> None:
        state = self._populated().with_declined("tobacco_use")
        summary = build(state, coverage=compute(state, machine.plan(state)))
        assert any("declined to answer" in line.text for line in summary.unresolved)

    def test_a_low_confidence_document_is_flagged_for_verification(
        self, machine: ClinicalStateMachine
    ) -> None:
        state = self._populated().with_document(
            DocumentRecord(
                document_id="scan1",
                kind="prescription",
                uploaded_at=NOW,
                processed=True,
                low_confidence=True,
            )
        )
        summary = build(state, coverage=compute(state, machine.plan(state)))
        assert any("low confidence" in line.text for line in summary.unresolved)

    def test_the_report_opens_with_the_draft_disclaimer(
        self, machine: ClinicalStateMachine
    ) -> None:
        state = self._populated()
        text = build(state, coverage=compute(state, machine.plan(state))).render_text()
        assert text.startswith("DRAFT PRE-CONSULTATION INTAKE")
        assert "no diagnosis and no clinical advice" in text

    def test_the_report_contains_no_unsupported_assertion(
        self, machine: ClinicalStateMachine
    ) -> None:
        """Target: zero. Always."""
        state = self._populated()
        summary = build(state, coverage=compute(state, machine.plan(state)))
        assert summary.unsupported_assertions() == ()
        assert find_unsupported_assertions(summary.render_text()) == ()

    def test_conflicts_and_alerts_render_in_the_report(
        self, machine: ClinicalStateMachine, content: ClinicalContent
    ) -> None:
        from app.domain.redflags.evaluator import evaluate

        state = self._populated().apply_record(
            make_fact(
                "known_diabetes",
                status=FactStatus.PRESENT,
                section=Section.PAST_MEDICAL,
                source_type=SourceType.DOCUMENT,
                fact_id="d1",
                display="Diabetes",
            )
        )
        summary = build(
            state,
            coverage=compute(state, machine.plan(state)),
            conflicts=detect(state),
            alerts=evaluate(state, content.red_flags),
        )
        text = summary.render_text()
        assert "INFORMATION CONFLICT" in text
        assert "SAFETY" in text

    def test_a_report_with_no_alerts_says_so_explicitly(
        self, machine: ClinicalStateMachine
    ) -> None:
        state = self._populated()
        text = build(state, coverage=compute(state, machine.plan(state))).render_text()
        assert "No urgent clinical review criteria triggered." in text

    def test_sections_render_in_standard_clinical_order(
        self, machine: ClinicalStateMachine
    ) -> None:
        state = self._populated()
        text = build(state, coverage=compute(state, machine.plan(state))).render_text()
        order = [
            "CHIEF COMPLAINT",
            "HISTORY OF PRESENTING ILLNESS",
            "PAST MEDICAL HISTORY",
            "ALLERGIES",
            "UNRESOLVED",
            "INFORMATION CONFLICTS",
            "SAFETY",
        ]
        positions = [text.index(heading) for heading in order]
        assert positions == sorted(positions)
