"""The patient app's record, through the real normalizer — 2/3 §9, §15 item 3.

§9 requires the app's output to validate against the same contract the Jetson's
does. Two copies of a contract drift, so this does not describe the app's output
— it **reads the app's own golden file** (`app/test/golden/app_record_0.1.json`,
written by `app/test/record_test.dart`) and puts it through
`app.normalize.registry.normalize`, the same function that handles a kiosk
payload in production.

Drift fails in both directions. Change the Dart without regenerating the golden
and the Flutter test fails; regenerate it into something this backend cannot
read and this fails.

If the app is not checked out, the tests skip rather than pass silently — a
contract test that quietly disappears is worse than one that is absent.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.domain.record import Certainty, FieldStatus
from app.normalize.registry import normalize

GOLDEN = (
    Path(__file__).resolve().parents[3] / "app" / "test" / "golden" / "app_record_0.1.json"
)

pytestmark = pytest.mark.skipif(
    not GOLDEN.is_file(),
    reason=f"the patient app's golden record is not present at {GOLDEN}",
)


@pytest.fixture(scope="module")
def payload() -> dict[str, Any]:
    return dict(json.loads(GOLDEN.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def record(payload: dict[str, Any]) -> Any:
    return normalize(payload, now=datetime(2026, 9, 3, 12, 0, tzinfo=UTC))


class TestTheBackendAcceptsIt:
    def test_it_normalises_without_repair(self, record: Any) -> None:
        """Straight through the front door.

        If an app record needed the repair path, every app intake would be
        marked `repaired` and every field it touched flagged for the physician —
        which would be true and useless.
        """
        assert record.intake_id
        assert record.provenance.repaired is False

    def test_the_schema_version_is_one_this_build_normalises(
        self, payload: dict[str, Any]
    ) -> None:
        assert payload["schema_version"] == "0.1"

    def test_the_hospital_and_department_survive(self, record: Any) -> None:
        assert record.department_code == "kayachikitsa"


class TestTheFiveStatusesSurvive:
    def test_each_one_arrives_as_itself(self, record: Any) -> None:
        """§15 item 4, checked at the far end of the pipe.

        The app can keep them distinct all it likes; what matters is that they
        are still distinct after normalisation.
        """
        by_field = {f.field_id: f for f in record.live_facts()}
        assert by_field["chief_complaint"].status is FieldStatus.ANSWERED
        assert by_field["tobacco"].status is FieldStatus.REFUSED
        assert by_field["alcohol"].status is FieldStatus.UNRESOLVED
        assert by_field["pregnancy"].status is FieldStatus.NOT_APPLICABLE
        assert by_field["breathlessness"].status is FieldStatus.NOT_ASKED

    def test_no_unsettled_field_acquires_a_value(self, record: Any) -> None:
        """The collapse this whole vocabulary exists to prevent."""
        for fact in record.live_facts():
            if fact.status is not FieldStatus.ANSWERED:
                assert fact.value is None, f"{fact.field_id} has a value it should not"


class TestTheValuesCoerceCorrectly:
    def test_a_duration_becomes_a_duration(self, record: Any) -> None:
        """`{"n": 3, "unit": "day"}` — the shape the normalizer reads.

        A tagged union like `{"kind": "duration", ...}` would coerce to a `Text`
        of the whole object, which is the exact drift this test exists to catch.
        """
        fact = next(f for f in record.live_facts() if f.field_id == "duration")
        assert fact.value is not None
        assert fact.value.model_dump()["kind"] == "duration"

    def test_a_scale_becomes_a_scale(self, record: Any) -> None:
        fact = next(f for f in record.live_facts() if f.field_id == "severity")
        assert fact.value is not None
        assert fact.value.model_dump()["kind"] == "scale"

    def test_a_chosen_option_keeps_its_code(self, record: Any) -> None:
        """The bare option string becomes a `Coded` value with the code intact.

        `rendered_value()` de-underscores for display — "abdominal pain" — which
        is the report renderer doing its job. What must survive verbatim is the
        code, because that is what the ontology and the red-flag rules match on.
        """
        fact = next(f for f in record.live_facts() if f.field_id == "chief_complaint")
        assert fact.value is not None
        assert fact.value.model_dump() == {
            "kind": "coded",
            "code": "abdominal_pain",
            "system": None,
            "display": None,
        }


class TestProvenance:
    def test_the_patients_own_words_survive(self, record: Any) -> None:
        """`original_text` travels with every fact — backend §4.

        The patient tapped a Hindi option; what the physician sees is the Hindi.
        """
        fact = next(f for f in record.live_facts() if f.field_id == "chief_complaint")
        assert fact.original_text == "पेट में दर्द"

    def test_a_tapped_answer_is_not_reported_as_confirmed(self, record: Any) -> None:
        """A patient's tap is a report, not a confirmation.

        Only physician verification produces `CONFIRMED`, and an app record
        arriving pre-confirmed would be the certainty increase the record model
        exists to prevent.
        """
        for fact in record.live_facts():
            assert fact.certainty is not Certainty.CONFIRMED

    def test_the_content_version_is_recorded(self, record: Any) -> None:
        """Which questions produced this answer, answerable months later."""
        assert record.provenance.content_version == "questions-2026-09-01"


class TestTheRedFlagAbortPath:
    def test_a_partial_record_still_normalises(self) -> None:
        """§6.3: submitted partial, with `aborted_red_flag`.

        A patient being sent to an emergency department is exactly when the
        hospital most wants the answers that sent them there — so this path must
        not be the one that fails to parse.
        """
        payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
        payload["status"] = "aborted_red_flag"
        payload["red_flags"] = [
            {
                "rule_id": "acute_chest_pain_with_dyspnoea",
                "severity": "critical",
                "fired_at": "2026-09-03T10:18:00Z",
                "triggering_fields": {"dyspnoea": "हाँ"},
            }
        ]
        record = normalize(payload, now=datetime(2026, 9, 3, 12, 0, tzinfo=UTC))
        assert record.red_flags
        assert record.live_facts()
