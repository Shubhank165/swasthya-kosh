from medikiosk.kiosk import differential
from medikiosk.models import PatientState


def test_no_findings_produces_no_differential() -> None:
    assert differential.build(PatientState(complaint="knee pain")) is None


def test_stroke_findings_rank_stroke_first() -> None:
    result = differential.build(
        PatientState(complaint="weakness", one_sided_weakness=True, speech_difficulty=True)
    )
    assert result["ranked"], "expected a ranked differential"
    assert "Stroke" in result["ranked"][0]["name"]
    assert result["ranked"][0]["icd10"]


def test_a_denial_on_a_select_node_is_dropped_not_scored_as_positive() -> None:
    """normalise_answer returns YES for any non-empty value on SINGLE_SELECT, so passing our
    False straight through would score a patient who denied fever as having it."""

    denied = differential.build(PatientState(complaint="knee pain", fever=False, vomiting=False))
    assert denied is None, "denials on select-type nodes must not become findings"

    # The same fields as positives do produce findings, proving the mapping is wired at all.
    reported = differential.build(PatientState(complaint="fever", fever=True, vomiting=True))
    assert set(reported["from_findings"]) == {"fever", "vomiting"}


def test_binary_nodes_still_carry_denials() -> None:
    """BINARY nodes encode False as -0.5, which is real evidence and must be kept."""

    result = differential.build(PatientState(complaint="chest pain", breathlessness=False))
    assert result is not None
    assert result["from_findings"] == ["breathlessness"]


def test_sweating_is_not_mapped_to_night_sweats() -> None:
    """Diaphoresis is not a night sweat. Mapping it to ROS_CON_004 ranked Pulmonary TB and
    Lymphoma at 50% each for a textbook MI while STEMI scored zero."""

    assert not any(field == "sweating" for field, _ in differential.FIELD_NODES)
    result = differential.build(PatientState(complaint="chest pain", sweating=True))
    assert result is None, "sweating alone must not drive a differential"


def test_confidence_is_reported_as_low_on_few_findings() -> None:
    """Three findings saturate the softmax to 1.000. The sheet must say so next to the number."""

    result = differential.build(
        PatientState(complaint="chest pain", chest_pain=True, breathlessness=True,
                     pain_radiation=True)
    )
    assert result["findings_count"] == 3
    assert result["confidence"] == "low"
    assert "not calibrated" in result["disclaimer"]


def test_fhir_bundle_is_provisional_and_carries_no_identifier() -> None:
    state = PatientState(complaint="weakness", one_sided_weakness=True, age_years=70)
    bundle = differential.fhir_bundle(state, differential.build(state))
    assert bundle["resourceType"] == "Bundle"
    conditions = [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Condition"]
    assert conditions, "expected at least one Condition"
    for condition in conditions:
        status = condition["verificationStatus"]["coding"][0]["code"]
        assert status == "provisional", "kiosk output must never be a confirmed diagnosis"
    patient = bundle["entry"][0]["resource"]
    assert "identifier" not in patient and "name" not in patient
