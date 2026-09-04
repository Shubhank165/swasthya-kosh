"""Deterministic repair provider.

Restructures a malformed payload by rule rather than by model, so the repair
*path* — validate, repair, re-validate, flag, or store raw and stop — is
exercised in every test run with no network and no nondeterminism.

It performs exactly the restructurings the real instruction permits, and it is
useful precisely because it is incapable of more:

- a field given as a bare value gets wrapped as `{"value": ..., "status":
  "answered"}`,
- a field with no `status` is marked **`unresolved`**, never `answered`, because
  a field whose status nobody recorded is a field whose answer nobody bound,
- a valueless status carrying a value has the value dropped, not the status
  raised,
- a missing `schema_version` is filled from the payload's shape.

It never invents a value. Neither may the real one.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

VALUELESS_STATUSES = frozenset({"unresolved", "not_asked", "not_applicable", "refused"})
KNOWN_STATUSES = VALUELESS_STATUSES | {"answered"}


class MockRepairProvider:
    """Rule-based repair. No model, no network, fully deterministic."""

    name = "mock"

    async def repair(
        self, payload: dict[str, Any], *, schema: dict[str, Any], errors: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        repaired = dict(payload)

        repaired.setdefault("schema_version", "0.1")
        if not repaired.get("status"):
            # An intake with no stated outcome is a partial one. Calling it
            # complete would assert the interview finished, which is precisely
            # the certainty this path may not add.
            repaired["status"] = "partial"
        if not repaired.get("language"):
            repaired["language"] = "en"
        if not repaired.get("reporter"):
            repaired["reporter"] = "self"

        fields = repaired.get("fields")
        if isinstance(fields, Mapping):
            repaired["fields"] = {
                str(name): _repair_field(body) for name, body in fields.items()
            }

        turns = repaired.get("turns")
        if isinstance(turns, list):
            repaired["turns"] = [
                turn for turn in turns if isinstance(turn, Mapping) and "turn_id" in turn
            ]

        flags = repaired.get("red_flags")
        if isinstance(flags, list):
            repaired["red_flags"] = [
                dict(flag)
                for flag in flags
                if isinstance(flag, Mapping) and flag.get("rule_id")
            ]

        return repaired


def _repair_field(body: Any) -> dict[str, Any]:
    """One field, restructured. Never given a value it did not arrive with."""
    if not isinstance(body, Mapping):
        # A bare value: `{"severity": 7}`. The value is real, so it is kept and
        # the status is the one that says an answer was bound.
        return {"value": body, "status": "answered"} if body is not None else {
            "value": None,
            "status": "unresolved",
        }

    field = dict(body)
    status = field.get("status")
    if status not in KNOWN_STATUSES:
        # No status, or one this build does not know. Both mean the same thing
        # for our purposes: nobody told us an answer was bound.
        field["status"] = "answered" if field.get("value") is not None else "unresolved"
    if field["status"] in VALUELESS_STATUSES:
        field["value"] = None
    return field
