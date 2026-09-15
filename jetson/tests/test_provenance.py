"""Provenance is a safety property, not a feature.

A doctor who cannot tell a spoken answer from an OCR guess will trust them equally, so these tests
guard the distinctions the report depends on.
"""

import pytest

from medikiosk.kiosk.flow import KioskFlow, Stage
from medikiosk.kiosk.provenance import Ledger, Source


def test_machine_derived_values_are_flagged_for_review() -> None:
    ledger = Ledger()
    ledger.record("complaint", "chest pain", Source.PATIENT_REPORTED)
    ledger.record("medication", "Metformin 500 mg", Source.OCR, confidence=0.62)
    ledger.record("medication", "Aspirin 75 mg", Source.OCR, confidence=0.97)

    review = ledger.review_queue()
    assert [entry.value for entry in review] == ["Metformin 500 mg"]
    # A person stating something is never queued for review, whatever it is.
    assert all(entry.source is not Source.PATIENT_REPORTED for entry in review)


def test_ocr_without_a_confidence_is_treated_as_unverified() -> None:
    """A missing score is not a good score. Defaulting it to trusted is how bad OCR reaches a
    doctor unchallenged."""

    ledger = Ledger()
    ledger.record("medication", "Augmentin 625 mg", Source.OCR)
    assert len(ledger.review_queue()) == 1


def test_correction_supersedes_and_never_destroys_the_original() -> None:
    ledger = Ledger()
    original = ledger.record("medication", "Metformin 600 mg", Source.OCR, confidence=0.71)
    ledger.correct("medication", "Metformin 500 mg", by="dr.mehta")

    current = ledger.current("medication")
    assert current.value == "Metformin 500 mg"
    assert current.source is Source.DOCTOR_VERIFIED
    assert current.corrected_by == "dr.mehta"

    # The OCR reading is still there, marked as replaced, so the extraction stays auditable.
    assert original.superseded_by == "dr.mehta"
    assert any(e.value == "Metformin 600 mg" for e in ledger.entries)
    assert len(ledger.review_queue()) == 0


def test_disagreement_between_sources_is_surfaced_not_resolved() -> None:
    """An ABHA record saying penicillin allergy and a patient saying none is exactly the conflict
    a doctor needs to see. Silently picking one would hide it."""

    ledger = Ledger()
    ledger.record("allergy", "penicillin", Source.ABHA)
    ledger.record("allergy", "none", Source.PATIENT_REPORTED)

    conflicts = ledger.conflicts("allergy")
    assert len(conflicts) == 2
    # The more trusted source is what current() offers, but both remain live.
    assert ledger.current("allergy").source is Source.ABHA


def test_no_conflict_reported_when_sources_agree() -> None:
    ledger = Ledger()
    ledger.record("allergy", "penicillin", Source.ABHA)
    ledger.record("allergy", "penicillin", Source.PATIENT_REPORTED)
    assert ledger.conflicts("allergy") == []


def test_a_representative_is_recorded_as_second_hand() -> None:
    flow = KioskFlow()
    flow.choose_language("hi")
    flow.set_abha(None)
    flow.set_who("other")
    assert flow.spoken_source is Source.REPRESENTATIVE_REPORTED

    direct = KioskFlow()
    direct.choose_language("hi")
    direct.set_abha(None)
    direct.set_who("self")
    assert direct.spoken_source is Source.PATIENT_REPORTED


def test_flow_records_questionnaire_and_document_sources() -> None:
    from medikiosk.kiosk import ayurveda

    flow = KioskFlow()
    flow.choose_language("hi")
    flow.set_abha(None)
    flow.set_who("self")
    flow.advance()
    assert flow.stage is Stage.AYURVEDA

    first = ayurveda.QUESTIONS[0]
    flow.answer_ayurveda(first.id, first.options[0].value)
    assert flow.ledger.entries[-1].source is Source.QUESTIONNAIRE

    flow.add_document(["Tab Augmentin 625 mg BD"], seconds=1.7, confidence=0.8)
    document_entry = flow.ledger.entries[-1]
    assert document_entry.source is Source.OCR
    assert document_entry.confidence == 0.8


def test_past_visits_are_attributed_to_the_record_not_the_patient() -> None:
    flow = KioskFlow()
    flow.choose_language("hi")
    flow.set_abha("12345678901234", history=[{"complaint": "chest pain", "recorded_at": "2026-01-01"}])
    entry = flow.ledger.current("previous_complaint")
    assert entry is not None
    assert entry.source is Source.ABHA


def test_report_carries_the_ledger() -> None:
    from medikiosk.kiosk import report
    from medikiosk.models import PatientState

    ledger = Ledger()
    ledger.record("complaint", "chest pain", Source.PATIENT_REPORTED)
    ledger.record("medication", "Metformin 500 mg", Source.OCR, confidence=0.5)

    built = report.build(PatientState(complaint="chest pain"), [], ledger=ledger)
    assert built["provenance"]["by_source"]["PATIENT_REPORTED"] == 1
    assert built["provenance"]["needs_review"] == 1
    assert built["provenance"]["review"][0]["value"] == "Metformin 500 mg"


def test_confidence_outside_zero_to_one_is_rejected() -> None:
    ledger = Ledger()
    with pytest.raises(ValueError):
        ledger.record("medication", "x", Source.OCR, confidence=1.5)
