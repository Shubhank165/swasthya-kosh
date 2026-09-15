"""OCR misreads doses, and a wrong dose is the most dangerous thing this system can show a
clinician. These tests pin the parser's precision, not just its recall."""

from medikiosk.kiosk import extraction


def test_parses_the_specification_worked_example() -> None:
    result = extraction.extract([
        "Tab Augmentin 625 mg BD x 5 days",
        "Paracetamol 500 mg SOS",
        "Diagnosis: Acute pharyngitis",
    ])

    augmentin, paracetamol = result["medications"]
    assert augmentin["name"] == "Augmentin"
    assert augmentin["strength"] == "625 mg"
    assert augmentin["frequency"] == "BD"
    assert augmentin["duration"] == "x 5 days"
    assert augmentin["form"] == "tab"

    assert paracetamol["name"] == "Paracetamol"
    assert paracetamol["frequency"] == "SOS"

    assert result["diagnoses"][0]["text"] == "Acute pharyngitis"


def test_numeric_indian_frequency_notation_is_understood() -> None:
    """1-0-1 means morning and night, and appears on prescriptions far more often than 'BD'."""

    result = extraction.extract(["Tab Metformin 500 mg 1-0-1 x 30 days"])
    assert result["medications"][0]["frequency"] == "1-0-1"


def test_lab_values_are_flagged_only_against_a_printed_range() -> None:
    """Built-in reference ranges vary by lab and population; applying the wrong one is worse than
    applying none."""

    result = extraction.extract([
        "Hemoglobin 10.2 g/dL (13-17)",
        "Creatinine 0.9 mg/dL",
    ])
    low, unranged = result["labs"]
    assert low["test"] == "Hemoglobin"
    assert low["value"] == 10.2
    assert low["flag"] == "low"
    assert unranged["flag"] is None, "no printed range means no flag, not a guess"


def test_prose_is_not_mistaken_for_a_prescription() -> None:
    """A bare word with no strength and no frequency is not a drug. Without this rule, 'Follow up
    after 5 days' becomes a medication called Follow."""

    result = extraction.extract([
        "Follow up after 5 days",
        "Patient advised rest",
        "Dr. A. Sharma MBBS",
    ])
    assert result["medications"] == []
    assert len(result["unparsed"]) == 3


def test_a_lab_line_is_not_claimed_as_a_medication() -> None:
    result = extraction.extract(["Hemoglobin 10.2 g/dL (13-17)"])
    assert result["medications"] == []
    assert len(result["labs"]) == 1


def test_unreadable_lines_are_reported_not_invented() -> None:
    result = extraction.extract(["Xy@@z ###", "Tab Aspirin 75 mg OD"])
    assert len(result["medications"]) == 1
    assert result["unparsed"] == ["Xy@@z ###"]
    assert result["parsed_count"] == 1


def test_confidence_rises_with_how_much_of_the_line_was_recognised() -> None:
    partial = extraction.extract(["Aspirin 75 mg"])["medications"][0]
    complete = extraction.extract(["Tab Aspirin 75 mg OD x 10 days"])["medications"][0]
    assert complete["confidence"] > partial["confidence"]
    assert complete["confidence"] <= 1.0


def test_every_result_carries_a_confirmation_warning() -> None:
    assert "clinician confirmation" in extraction.extract(["Tab Aspirin 75 mg OD"])["disclaimer"]
