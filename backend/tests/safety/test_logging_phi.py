"""Invariant 9: logs never contain clinical text.

This is the test that makes the invariant real. It writes every kind of clinical
value into a log call — a Hindi utterance, an English narrative, a drug name, a
patient name, a phone number — and asserts none of it reaches the emitted
record. Convention fails at 3am during a demo; this does not.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import pytest

from app.core.logging import (
    ALLOWLISTED_KEYS,
    DENYLISTED_KEYS,
    REDACTED,
    configure_logging,
    get_logger,
    phi_filter,
    scrub,
)

#: Strings that must never appear in any log line, whatever key they arrive under.
CLINICAL_TEXT: tuple[str, ...] = (
    "seene mein jalan aur saans phoolna",
    "सीने में जलन और साँस फूलना",
    "patient reports burning chest pain radiating to the left arm",
    "Type 2 Diabetes Mellitus since 2014",
    "metformin 500mg twice daily with meals",
    "Ramesh Kumar Sharma",
    "9876543210",
    "flat 4, sector 12, dwarka, new delhi",
)


class TestScrub:
    @pytest.mark.parametrize("text", CLINICAL_TEXT)
    def test_clinical_text_is_redacted_under_a_denylisted_key(self, text: str) -> None:
        assert scrub(text, key="original_expression") == REDACTED
        assert scrub(text, key="answer") == REDACTED
        assert scrub(text, key="summary") == REDACTED

    @pytest.mark.parametrize("text", CLINICAL_TEXT)
    def test_clinical_text_is_redacted_even_under_an_unexpected_key(self, text: str) -> None:
        """The key a leak arrives under is exactly the key nobody thought of."""
        assert scrub(text, key="some_new_field") == REDACTED

    def test_devanagari_is_always_redacted(self) -> None:
        """A patient's own words in their own script, under any key at all."""
        assert scrub("बुखार", key="concept") == REDACTED

    def test_identifiers_and_enums_pass_through(self) -> None:
        """The filter has to leave enough behind to debug with."""
        assert scrub("intake_0001", key="intake_id") == "intake_0001"
        assert scrub("present", key="status") == "present"
        assert scrub("chest_pain", key="concept") == "chest_pain"
        assert scrub("KC-014", key="token") == "KC-014"

    def test_numbers_and_booleans_pass_through(self) -> None:
        assert scrub(0.94, key="confidence") == 0.94
        assert scrub(12, key="count") == 12
        assert scrub(True, key="processed") is True

    def test_nested_structures_are_walked(self) -> None:
        payload = {
            "intake_id": "intake_1",
            "fact": {"concept": "chest_pain", "original_expression": "seene mein jalan"},
            "facts": [{"answer": "burning pain in my chest since morning"}],
        }
        cleaned = scrub(payload)
        assert cleaned["intake_id"] == "intake_1"
        assert cleaned["fact"]["concept"] == "chest_pain"
        assert cleaned["fact"]["original_expression"] == REDACTED
        assert cleaned["facts"][0]["answer"] == REDACTED

    def test_long_strings_are_redacted_even_without_spaces(self) -> None:
        assert scrub("x" * 80, key="unexpected") == REDACTED

    def test_denylist_and_allowlist_do_not_overlap(self) -> None:
        """An overlap would make behaviour depend on evaluation order."""
        assert set() == DENYLISTED_KEYS & ALLOWLISTED_KEYS


class TestProcessor:
    def test_the_processor_scrubs_every_field(self) -> None:
        cleaned = phi_filter(
            None,
            "info",
            {
                "event": "intake_updated",
                "intake_id": "intake_1",
                "original_expression": "seene mein jalan",
                "note": "patient reports burning chest pain since this morning",
            },
        )
        assert cleaned["event"] == "intake_updated"
        assert cleaned["intake_id"] == "intake_1"
        assert cleaned["original_expression"] == REDACTED
        assert cleaned["note"] == REDACTED


class TestEndToEnd:
    @pytest.mark.parametrize("text", CLINICAL_TEXT)
    def test_clinical_text_cannot_reach_an_emitted_log_record(self, text: str) -> None:
        """The full pipeline, exactly as production configures it."""
        configure_logging(level="INFO", json_output=True)
        logger = get_logger("test")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.info(
                "fact_recorded",
                intake_id="intake_1",
                concept="chest_pain",
                status="present",
                original_expression=text,
                answer=text,
                free_text=text,
                patient_name=text,
            )
        emitted = buffer.getvalue()
        assert text not in emitted
        assert "intake_1" in emitted
        assert "chest_pain" in emitted

    def test_an_emitted_record_is_still_valid_json_with_useful_fields(self) -> None:
        configure_logging(level="INFO", json_output=True)
        logger = get_logger("test")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            logger.info("ticket_called", ticket_id="tkt_1", token="KC-014", count=3)
        record = json.loads(buffer.getvalue().strip().splitlines()[-1])
        assert record["event"] == "ticket_called"
        assert record["ticket_id"] == "tkt_1"
        assert record["token"] == "KC-014"
        assert record["count"] == 3
