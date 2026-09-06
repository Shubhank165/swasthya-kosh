"""Schema 0.2: carry-forward provenance — 3/3 §B1.

The gap this closes is narrow and worth stating precisely. At 0.1, a returning
patient confirming "yes, still diabetic" produced a fact indistinguishable from
one first established today. Three things a physician needs to tell apart
collapsed into one:

- an answer given for the first time today;
- an answer from June that the patient confirmed this morning;
- an answer from June that nobody re-asked.

These tests hold that distinction open, and hold 0.1 working while they do it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts.kiosk.v0_2 import KioskIntakeV0_2
from app.domain.record import FactChannel, FieldStatus
from app.normalize.registry import normalize, supported_versions

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "kiosk"


def _payload() -> dict[str, Any]:
    with (FIXTURES / "0.2.json").open(encoding="utf-8") as handle:
        loaded: dict[str, Any] = json.load(handle)
    return loaded


class TestZeroPointOneKeepsWorking:
    """The promise of §4.2: a new version is additive, not a migration."""

    def test_both_versions_are_registered(self) -> None:
        assert supported_versions() == ("0.1", "0.2")

    def test_a_zero_one_payload_still_normalises(self) -> None:
        with (FIXTURES / "0.1.json").open(encoding="utf-8") as handle:
            record = normalize(json.load(handle), now=NOW)
        assert record.provenance.schema_version == "0.1"
        assert all(f.carried_forward is None for f in record.facts)

    def test_a_zero_one_payload_is_valid_zero_two_but_for_its_version(self) -> None:
        """Additive means exactly this: nothing was removed or tightened."""
        with (FIXTURES / "0.1.json").open(encoding="utf-8") as handle:
            payload = json.load(handle)
        payload["schema_version"] = "0.2"
        parsed = KioskIntakeV0_2.model_validate(payload)
        assert all(field.carried_forward is None for field in parsed.fields.values())


class TestCarriedForwardFacts:
    def test_a_confirmed_answer_records_all_three_parts(self) -> None:
        record = normalize(_payload(), now=NOW)
        fact = next(f for f in record.facts if f.field_id == "known_diabetes")
        assert fact.carried_forward is not None
        assert fact.carried_forward.originally_recorded.isoformat() == "2026-06-12"
        assert fact.carried_forward.confirmed_today is True
        assert fact.carried_forward.from_intake_id

    def test_not_re_asked_is_null_and_not_false(self) -> None:
        """`None` means nobody asked. `False` would mean the patient declined
        to confirm — a claim about a conversation that never happened."""
        record = normalize(_payload(), now=NOW)
        fact = next(f for f in record.facts if f.field_id == "drug_allergy")
        assert fact.carried_forward is not None
        assert fact.carried_forward.confirmed_today is None

    def test_it_is_filed_under_prior_record_not_voice(self) -> None:
        """Otherwise the contradiction detector compares June with June.

        The detector's whole job is what the patient says today against what we
        already held. A carried answer filed as today's speech is on both sides
        of that comparison and can never conflict with anything.
        """
        record = normalize(_payload(), now=NOW)
        fact = next(f for f in record.facts if f.field_id == "known_diabetes")
        assert fact.channel is FactChannel.PRIOR_RECORD
        assert fact.is_from_record is True
        assert fact.is_from_today is False

    def test_confirming_does_not_raise_certainty(self) -> None:
        """A patient saying "yes, still" is a report, exactly as it was in June."""
        record = normalize(_payload(), now=NOW)
        fact = next(f for f in record.facts if f.field_id == "known_diabetes")
        assert fact.certainty.value == "reported"
        assert fact.physician_verified is False

    def test_the_source_links_back_to_the_previous_intake(self) -> None:
        """§5: the evidence panel opens that visit."""
        record = normalize(_payload(), now=NOW)
        fact = next(f for f in record.facts if f.field_id == "known_diabetes")
        assert getattr(fact.source, "prior_intake_id", None) == (
            fact.carried_forward.from_intake_id if fact.carried_forward else None
        )

    def test_a_field_answered_today_carries_nothing(self) -> None:
        record = normalize(_payload(), now=NOW)
        fact = next(f for f in record.facts if f.field_id == "chief_complaint")
        assert fact.carried_forward is None
        assert fact.channel is FactChannel.VOICE


class TestTheContractRefusesTheImpossible:
    @pytest.mark.parametrize("status", ["not_asked", "unresolved", "refused"])
    def test_an_unanswered_field_cannot_carry_one_forward(self, status: str) -> None:
        """A device saying both "never asked" and "brought over from June" has
        contradicted itself, and guessing which half is true would put a value
        on the record that nobody established."""
        payload = _payload()
        payload["fields"]["known_diabetes"] = {
            "status": status,
            "carried_forward": {
                "from_intake_id": "x",
                "originally_recorded": "2026-06-12",
            },
        }
        with pytest.raises(ValidationError):
            KioskIntakeV0_2.model_validate(payload)

    def test_a_carry_forward_without_a_date_is_refused(self) -> None:
        """"From a previous visit" with no date is not provenance."""
        payload = _payload()
        payload["fields"]["known_diabetes"]["carried_forward"] = {"from_intake_id": "x"}
        with pytest.raises(ValidationError):
            KioskIntakeV0_2.model_validate(payload)


class TestItReachesTheApi:
    def test_the_fact_carries_its_provenance_to_the_dashboard(self) -> None:
        """§4.2's carried-forward rendering has nothing to render without it."""
        from app.api.serialise import fact_out
        from app.domain.report.builder import FieldLabels

        record = normalize(_payload(), now=NOW)
        fact = next(f for f in record.facts if f.field_id == "known_diabetes")
        out = fact_out(fact, labels=FieldLabels({}))
        assert out.carried_forward == {
            "from_intake_id": fact.carried_forward.from_intake_id,  # type: ignore[union-attr]
            "originally_recorded": "2026-06-12",
            "confirmed_today": True,
        }
        assert out.status == FieldStatus.ANSWERED.value
