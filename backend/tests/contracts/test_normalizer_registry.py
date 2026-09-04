"""Normalizer contract tests — §13.4.

Every registered schema version is checked against a golden fixture. **Adding a
version without a fixture fails the suite**, which is the mechanism that keeps
§4.2's three-step procedure honest: the third step is one registry line, and
this test is what makes forgetting the first two loud.

The golden files are the readable part of a schema change. A 0.2 normalizer that
quietly stops carrying `original_text` shows up here as a diff, in a file a
reviewer can read, rather than as an absence somebody notices in a report three
weeks later.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.domain.record import CanonicalRecord, FieldStatus
from app.normalize.registry import (
    NORMALIZERS,
    UnsupportedSchemaVersion,
    normalize,
    supported_versions,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "kiosk"

#: The same instant for every version, so a golden file diff is a mapping change
#: and never a clock change.
NOW = datetime(2026, 9, 3, 10, 21, 5, tzinfo=UTC)


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        loaded: dict[str, Any] = json.load(handle)
    return loaded


def _canonical_json(record: CanonicalRecord) -> str:
    return json.dumps(
        record.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False
    )


class TestRegistry:
    def test_every_registered_version_has_a_fixture(self) -> None:
        """A version in the registry with no golden fixture fails here.

        This is the guard the brief asks for. Without it, `registry.py` is a
        dict anyone can add to, and the promise that adding a version is three
        cheap edits quietly becomes a promise that it is three cheap *untested*
        edits.
        """
        missing = [
            version
            for version in supported_versions()
            if not (FIXTURES / f"{version}.json").is_file()
        ]
        assert missing == [], (
            f"registered schema versions with no fixture in {FIXTURES}: {missing}. "
            "Add tests/fixtures/kiosk/<version>.json and its .expected.json."
        )

    def test_every_fixture_has_a_normalizer(self) -> None:
        """And the other direction: a stray fixture means a half-finished version."""
        orphans = [
            path.stem
            for path in FIXTURES.glob("*.json")
            if not path.name.endswith(".expected.json") and path.stem not in NORMALIZERS
        ]
        assert orphans == []

    def test_unknown_version_is_rejected(self) -> None:
        with pytest.raises(UnsupportedSchemaVersion) as caught:
            normalize({"schema_version": "9.9"}, now=NOW)
        assert caught.value.details["schema_version"] == "9.9"
        assert "0.1" in caught.value.details["supported"]

    def test_missing_version_is_rejected(self) -> None:
        """A payload with no `schema_version` cannot be guessed at.

        Assuming the latest version would mean silently normalising a payload
        under rules it was not written for.
        """
        with pytest.raises(UnsupportedSchemaVersion):
            normalize({"intake_id": "x"}, now=NOW)


@pytest.mark.parametrize("version", supported_versions())
class TestGoldenFixtures:
    def test_matches_expected_record(self, version: str) -> None:
        """The fixture normalises to exactly the recorded canonical record."""
        payload = _load(FIXTURES / f"{version}.json")
        record = normalize(payload, now=NOW)
        expected_path = FIXTURES / f"{version}.expected.json"

        actual = _canonical_json(record)
        if not expected_path.is_file():
            expected_path.write_text(actual + "\n", encoding="utf-8")
            pytest.fail(
                f"wrote a new golden file at {expected_path}. Review it and re-run — "
                "a golden file that appears without being read is not a test."
            )
        assert actual == expected_path.read_text(encoding="utf-8").rstrip("\n")

    def test_normalizing_twice_is_identical(self, version: str) -> None:
        """Normalizers are pure. Same input, same output, every time.

        Fact ids are derived from the payload rather than generated, which is
        what makes ingest idempotent and the golden files stable.
        """
        payload = _load(FIXTURES / f"{version}.json")
        assert _canonical_json(normalize(payload, now=NOW)) == _canonical_json(
            normalize(payload, now=NOW)
        )

    def test_no_field_is_dropped(self, version: str) -> None:
        """Every field in the payload reaches the record.

        A field that vanishes between the kiosk and the canonical record is a
        question the patient answered for nothing.
        """
        payload = _load(FIXTURES / f"{version}.json")
        record = normalize(payload, now=NOW)
        assert {f.field_id for f in record.facts} == set(payload["fields"])

    def test_statuses_survive_verbatim(self, version: str) -> None:
        """The five-valued vocabulary crosses normalisation unchanged.

        Not "equivalently" — unchanged. `unresolved` is `unresolved`, and no
        mapping table stands between the payload and the record.
        """
        payload = _load(FIXTURES / f"{version}.json")
        record = normalize(payload, now=NOW)
        for field_id, body in payload["fields"].items():
            fact = next(f for f in record.facts if f.field_id == field_id)
            assert fact.status.value == body["status"], (
                f"{field_id}: kiosk said {body['status']!r}, record says "
                f"{fact.status.value!r}"
            )

    def test_original_text_is_preserved(self, version: str) -> None:
        """What the patient actually said travels with the normalised value."""
        payload = _load(FIXTURES / f"{version}.json")
        record = normalize(payload, now=NOW)
        for field_id, body in payload["fields"].items():
            if not body.get("original_text"):
                continue
            fact = next(f for f in record.facts if f.field_id == field_id)
            assert fact.original_text == body["original_text"]

    def test_unsettled_fields_carry_no_value(self, version: str) -> None:
        """Nothing acquires a value on the way through.

        The failure this catches is the one that matters most: a field the
        device could not settle arriving in the record with a value somebody's
        default filled in.
        """
        payload = _load(FIXTURES / f"{version}.json")
        record = normalize(payload, now=NOW)
        for fact in record.facts:
            if fact.status is not FieldStatus.ANSWERED:
                assert fact.value is None, (
                    f"{fact.field_id} is {fact.status} but carries "
                    f"{fact.rendered_value()!r}"
                )

    def test_red_flags_are_carried_not_evaluated(self, version: str) -> None:
        """Red flags in the payload arrive as events, unchanged and unacknowledged."""
        payload = _load(FIXTURES / f"{version}.json")
        record = normalize(payload, now=NOW)
        assert [e.rule_id for e in record.red_flags] == [
            f["rule_id"] for f in payload.get("red_flags", [])
        ]
        assert all(not e.is_acknowledged for e in record.red_flags)
