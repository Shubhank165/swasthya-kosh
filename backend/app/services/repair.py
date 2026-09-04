"""The repair path — the one place a language model is allowed.

```
payload → validate against contract
            ├─ valid   → normalize → canonical record          (no model call)
            └─ invalid → repair with LLM → re-validate
                           ├─ valid   → normalize, flag repaired
                           └─ invalid → persist raw, mark needs_manual_review
```

The valid path never calls a model. That is most payloads, and it is why the
repair rate is a meaningful number: it counts how often the Jetson's
keyword/regex extractor produced something this service could not read, and it
should fall as the extractor improves.

Three constraints on the model, enforced here rather than trusted to the prompt:

1. **Structured output with the schema enforced.** The model cannot return prose.
2. **Re-validation, unconditionally.** Whatever comes back is validated against
   the same contract as the original. The instruction is not evidence.
3. **Every field the repair touched is stamped `repaired = True`**, renders with
   a marker, and can never be `physician_verified` at ingest. A repaired field
   is a field a machine restructured; it is not a field anyone confirmed.

If repair also fails, the raw payload is stored and the intake is marked
`needs_manual_review`. **Input is never discarded.**
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.adapters.protocols import RepairProvider
from app.contracts.kiosk.v0_1 import KioskIntakeV0_1
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Contract model per schema version. Grows with `app/normalize/registry.py`.
CONTRACTS: dict[str, type[KioskIntakeV0_1]] = {"0.1": KioskIntakeV0_1}


@dataclass(frozen=True, slots=True)
class RepairOutcome:
    """What the repair path produced."""

    #: The payload to normalise, or `None` when repair failed or was skipped.
    payload: Mapping[str, Any] | None
    #: True when a model call actually restructured something.
    repaired: bool = False
    #: Structural validation errors. Never the payload's clinical text — this
    #: reaches a log and an `ingest_raw` row.
    errors: tuple[dict[str, Any], ...] = ()
    #: `ok` | `repaired` | `repair_failed` | `repair_disabled` | `unsupported_version`
    reason: str = "ok"
    #: Fields the repair changed, so the normalizer can stamp them.
    touched_fields: frozenset[str] = field(default_factory=frozenset)


def contract_for(version: object) -> type[KioskIntakeV0_1] | None:
    return CONTRACTS.get(version) if isinstance(version, str) else None


def safe_errors(exc: ValidationError) -> tuple[dict[str, Any], ...]:
    """Validation errors with the offending values stripped.

    Pydantic's errors carry `input`, which for a clinical payload is the
    patient's own words. Those go in `ingest_raw`, which is access-controlled;
    they do not go in the error list, which goes in a log line.
    """
    return tuple(
        {
            "loc": [str(part) for part in error["loc"]],
            "type": error["type"],
            "msg": error["msg"],
        }
        for error in exc.errors()
    )


def validate(payload: Mapping[str, Any]) -> tuple[bool, tuple[dict[str, Any], ...]]:
    """Whether `payload` satisfies its declared contract."""
    contract = contract_for(payload.get("schema_version"))
    if contract is None:
        return False, (
            {
                "loc": ["schema_version"],
                "type": "unsupported_version",
                "msg": f"no contract for schema_version {payload.get('schema_version')!r}",
            },
        )
    try:
        contract.model_validate(payload)
    except ValidationError as exc:
        return False, safe_errors(exc)
    return True, ()


def _changed_fields(
    original: Mapping[str, Any], repaired: Mapping[str, Any]
) -> frozenset[str]:
    """Which entries under `fields` the repair altered.

    Used to stamp exactly those facts `repaired`, rather than the whole record.
    A payload that failed on one malformed field should not demote the other
    nineteen, which arrived perfectly well-formed and were not touched.
    """
    before = original.get("fields")
    after = repaired.get("fields")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return frozenset(after) if isinstance(after, Mapping) else frozenset()
    return frozenset(
        name for name, body in after.items() if before.get(name) != body
    )


async def attempt(
    payload: Mapping[str, Any],
    *,
    provider: RepairProvider | None,
    max_attempts: int = 1,
) -> RepairOutcome:
    """Validate, and repair if needed.

    Returns a `RepairOutcome` in every case. It does not raise: a payload that
    cannot be repaired is an expected outcome with a defined handling, not an
    exception.
    """
    ok, errors = validate(payload)
    if ok:
        return RepairOutcome(payload=payload, repaired=False, reason="ok")

    if any(e["type"] == "unsupported_version" for e in errors):
        # A device running ahead of the backend. Repair cannot help — there is
        # no target schema to repair *to*. Store it and ship the normalizer.
        return RepairOutcome(
            payload=None, errors=errors, reason="unsupported_version"
        )

    if provider is None:
        logger.info("repair_skipped_disabled", error_code="contract_invalid")
        return RepairOutcome(payload=None, errors=errors, reason="repair_disabled")

    contract = contract_for(payload.get("schema_version"))
    assert contract is not None  # unsupported_version returned above
    schema = contract.model_json_schema()

    current: Mapping[str, Any] = payload
    current_errors = errors
    for attempt_number in range(1, max_attempts + 1):
        candidate = await provider.repair(
            dict(current), schema=schema, errors=[dict(e) for e in current_errors]
        )
        if candidate is None:
            break
        ok, current_errors = validate(candidate)
        if ok:
            logger.info(
                "repair_succeeded", attempt=attempt_number, provider=provider.name
            )
            return RepairOutcome(
                payload=candidate,
                repaired=True,
                reason="repaired",
                touched_fields=_changed_fields(payload, candidate),
            )
        current = candidate

    logger.warning("repair_failed", provider=provider.name, count=len(current_errors))
    return RepairOutcome(payload=None, errors=current_errors, reason="repair_failed")
