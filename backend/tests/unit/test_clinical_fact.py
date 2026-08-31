"""Facts, statuses and the certainty invariants."""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.clinical.enums import (
    ANSWERED_STATUSES,
    Certainty,
    FactStatus,
    ReporterRole,
    SourceType,
    certainty_rank,
)
from app.domain.clinical.fact import CertaintyIncreaseError
from app.domain.clinical.provenance import (
    BoundingBox,
    CodedValue,
    DateValue,
    Duration,
    FactId,
    Quantity,
    ScaleValue,
    SourceRef,
    TextValue,
)
from tests.conftest import START, make_fact


class TestFiveValueStatus:
    """Invariant 5: five statuses, never a boolean."""

    def test_all_five_statuses_are_distinct(self) -> None:
        assert len(set(FactStatus)) == 5

    def test_not_asked_is_not_absent(self) -> None:
        """The distinction the whole system rests on: we never asked about the
        allergy, versus the patient denied one."""
        not_asked = make_fact("drug_allergy", status=FactStatus.NOT_ASKED)
        absent = make_fact("drug_allergy", status=FactStatus.ABSENT, fact_id="f2")
        assert not_asked.status is not absent.status
        assert not not_asked.is_answered
        assert absent.is_answered

    def test_unknown_counts_as_answered_but_not_asserted(self) -> None:
        """"I don't know" is a real answer — the question was put and settled —
        but it asserts nothing."""
        fact = make_fact("known_diabetes", status=FactStatus.UNKNOWN)
        assert fact.is_answered
        assert not fact.is_asserted

    def test_answered_statuses_exclude_not_asked_and_not_applicable(self) -> None:
        assert FactStatus.NOT_ASKED not in ANSWERED_STATUSES
        assert FactStatus.NOT_APPLICABLE not in ANSWERED_STATUSES

    @pytest.mark.parametrize(
        "status", [FactStatus.NOT_ASKED, FactStatus.NOT_APPLICABLE, FactStatus.ABSENT]
    )
    def test_valueless_statuses_reject_a_value(self, status: FactStatus) -> None:
        """Absence has no magnitude: an ABSENT fact carrying a value would read
        as a finding in every downstream renderer."""
        with pytest.raises(ValueError, match="must not carry a value"):
            make_fact("severity", status=status, value=ScaleValue(7, 0, 10))


class TestCertaintyNeverIncreases:
    """Invariant 4: never silently increase certainty."""

    def test_revision_may_not_promote_certainty(self) -> None:
        fact = make_fact("duration", certainty=Certainty.APPROXIMATE)
        with pytest.raises(CertaintyIncreaseError, match="cannot promote certainty"):
            fact.revise(
                new_fact_id=FactId("f2"),
                recorded_at=START,
                certainty=Certainty.CONFIRMED,
            )

    def test_revision_may_lower_certainty(self) -> None:
        fact = make_fact("duration", certainty=Certainty.REPORTED)
        revised = fact.revise(
            new_fact_id=FactId("f2"), recorded_at=START, certainty=Certainty.UNCERTAIN
        )
        assert revised.certainty is Certainty.UNCERTAIN

    def test_patient_confirmation_is_the_one_legitimate_promotion(self) -> None:
        """A human re-affirming what we recorded is the only thing that may raise
        certainty, and it goes through a dedicated method that says so."""
        fact = make_fact("known_diabetes", certainty=Certainty.REPORTED)
        confirmed = fact.confirmed_by_patient(new_fact_id=FactId("f2"), recorded_at=START)
        assert confirmed.certainty is Certainty.CONFIRMED
        assert confirmed.patient_confirmed
        assert confirmed.supersedes == fact.fact_id

    def test_confirmation_does_not_imply_physician_verification(self) -> None:
        fact = make_fact("known_diabetes")
        confirmed = fact.confirmed_by_patient(new_fact_id=FactId("f2"), recorded_at=START)
        assert confirmed.patient_confirmed
        assert not confirmed.physician_verified

    def test_physician_verification_does_not_imply_patient_confirmation(self) -> None:
        fact = make_fact("known_diabetes")
        verified = fact.verified_by_physician(
            new_fact_id=FactId("f2"), recorded_at=START, physician_id="dr-1"
        )
        assert verified.physician_verified
        assert not verified.patient_confirmed
        assert "dr-1" in (verified.note or "")

    def test_confirmation_does_not_promote_an_approximate_answer(self) -> None:
        """Confirming "about two weeks" leaves it approximate. The patient
        re-affirmed a hedge; they did not sharpen it."""
        fact = make_fact("duration", certainty=Certainty.APPROXIMATE)
        confirmed = fact.confirmed_by_patient(new_fact_id=FactId("f2"), recorded_at=START)
        assert confirmed.certainty is Certainty.APPROXIMATE

    def test_a_revision_clears_prior_human_sign_off(self) -> None:
        """A new claim has not been confirmed or verified, whatever its
        predecessor carried."""
        fact = make_fact("severity", patient_confirmed=True, physician_verified=True)
        revised = fact.revise(
            new_fact_id=FactId("f2"), recorded_at=START, value=ScaleValue(8, 0, 10)
        )
        assert not revised.patient_confirmed
        assert not revised.physician_verified

    @given(
        first=st.sampled_from(list(Certainty)),
        second=st.sampled_from(list(Certainty)),
    )
    def test_revision_certainty_never_rises(self, first: Certainty, second: Certainty) -> None:
        fact = make_fact("duration", certainty=first)
        if certainty_rank(second) > certainty_rank(first):
            with pytest.raises(CertaintyIncreaseError):
                fact.revise(new_fact_id=FactId("f2"), recorded_at=START, certainty=second)
        else:
            assert (
                fact.revise(
                    new_fact_id=FactId("f2"), recorded_at=START, certainty=second
                ).certainty
                is second
            )


class TestOriginalExpressionSurvives:
    """Invariant 7: never destroy the patient's own words."""

    def test_original_expression_is_kept_beside_the_concept(self) -> None:
        """`"seene mein jalan"` is never replaced by `"burning chest pain"`."""
        fact = make_fact(
            "chest_pain",
            value=CodedValue(code="chest_pain", display="Chest pain"),
            original_expression="seene mein jalan",
            original_language="hi",
            display="Chest pain",
        )
        assert fact.original_expression == "seene mein jalan"
        assert fact.original_language == "hi"
        assert "Chest pain" in fact.display()

    def test_revision_carries_the_original_expression_forward(self) -> None:
        fact = make_fact(
            "chest_pain", original_expression="seene mein jalan", original_language="hi"
        )
        revised = fact.revise(new_fact_id=FactId("f2"), recorded_at=START)
        assert revised.original_expression == "seene mein jalan"


class TestProvenance:
    """Invariant 6: every fact carries provenance."""

    def test_transcript_ref_points_at_an_offset_span(self) -> None:
        fact = make_fact("chest_pain", source_type=SourceType.VOICE)
        assert fact.source_ref.transcript is not None
        assert fact.source_ref.transcript.end_ms >= fact.source_ref.transcript.start_ms

    def test_document_ref_points_at_a_page(self) -> None:
        fact = make_fact("known_diabetes", source_type=SourceType.DOCUMENT)
        assert fact.source_ref.document is not None
        assert fact.source_ref.document.page == 1

    def test_source_ref_requires_exactly_one_carrier(self) -> None:
        from app.domain.clinical.provenance import DocumentId, SegmentId, TranscriptRef

        with pytest.raises(ValueError, match="exactly one"):
            SourceRef(transcript=TranscriptRef(SegmentId("s"), 0, 1), entered_by="staff")
        with pytest.raises(ValueError, match="exactly one"):
            SourceRef()
        assert SourceRef.from_document(DocumentId("d"), 1).document is not None

    def test_staff_entered_facts_still_carry_provenance(self) -> None:
        """No exceptions, including for facts entered by staff."""
        fact = make_fact("age", source_type=SourceType.STAFF, reported_by=ReporterRole.STAFF)
        assert fact.source_ref.entered_by is not None

    def test_confidence_is_bounded(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            make_fact("severity", confidence=1.4)

    def test_bounding_box_is_normalised(self) -> None:
        BoundingBox(0.1, 0.2, 0.3, 0.4)
        with pytest.raises(ValueError, match=r"0\.0\.\.1\.0"):
            BoundingBox(1.4, 0.2, 0.3, 0.4)


class TestValueRendering:
    """Typed values keep the precision the patient actually gave."""

    def test_duration_keeps_the_unit_the_patient_used(self) -> None:
        """Two weeks stays two weeks. Normalising to 1209600 seconds would throw
        away the precision the patient expressed."""
        assert Duration(2, "weeks").render() == "2 weeks"
        assert Duration(1, "weeks").render() == "1 week"

    def test_quantity_requires_a_unit(self) -> None:
        with pytest.raises(ValueError, match="requires a unit"):
            Quantity(120, "")

    def test_scale_rejects_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="outside"):
            ScaleValue(11, 0, 10)
        assert ScaleValue(7, 0, 10).render() == "7/10"

    def test_year_precision_date_renders_as_a_year(self) -> None:
        """"Sometime in 2019" must not render as 1 January 2019."""
        assert DateValue(date(2019, 1, 1), precision="year").render() == "2019"
        assert DateValue(date(2019, 6, 4)).render() == "2019-06-04"

    def test_text_value_round_trips(self) -> None:
        assert TextValue("metformin 500mg").render() == "metformin 500mg"

    def test_duration_rejects_an_unknown_unit(self) -> None:
        with pytest.raises(ValueError, match="unsupported duration unit"):
            Duration(2, "fortnights")
