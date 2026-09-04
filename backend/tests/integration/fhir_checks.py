"""Offline structural checks for an R4 bundle.

Not a substitute for the published validator — that runs in
`tests/adapters/test_fhir.py` behind the `network` marker, because a suite that
cannot run on a train is a suite nobody runs. What this catches is the class of
error the validator would catch and that we can catch in milliseconds: a
dangling reference, a resource with no id, a `CodeableConcept` with a coding and
no system, a status outside its value set.

Kept in one module so the end-to-end test and the mapper's own tests assert the
same thing about the same bytes.
"""

from __future__ import annotations

import re
from typing import Any

#: The R4 `id` datatype. Underscores are not in it, and every internal id in
#: this system contains one — the published validator rejected the first bundle
#: this project produced for exactly that reason, so the rule is asserted here
#: too and the offline suite catches it next time.
R4_ID = re.compile(r"^[A-Za-z0-9.-]{1,64}$")

#: The R4 value sets this bundle actually uses. Enumerated rather than fetched:
#: the point is to fail when a mapper change emits something outside them.
STATUS_VALUE_SETS: dict[str, frozenset[str]] = {
    "Encounter": frozenset(
        {
            "planned",
            "arrived",
            "triaged",
            "in-progress",
            "onleave",
            "finished",
            "cancelled",
            "entered-in-error",
            "unknown",
        }
    ),
    "Observation": frozenset(
        {
            "registered",
            "preliminary",
            "final",
            "amended",
            "corrected",
            "cancelled",
            "entered-in-error",
            "unknown",
        }
    ),
    "MedicationStatement": frozenset(
        {
            "active",
            "completed",
            "entered-in-error",
            "intended",
            "stopped",
            "on-hold",
            "unknown",
            "not-taken",
        }
    ),
    "DocumentReference": frozenset(
        {"current", "superseded", "entered-in-error"}
    ),
}

#: `Condition.clinicalStatus` and `verificationStatus`.
CONDITION_CLINICAL = frozenset(
    {"active", "recurrence", "relapse", "inactive", "remission", "resolved"}
)
CONDITION_VERIFICATION = frozenset(
    {"unconfirmed", "provisional", "differential", "confirmed", "refuted", "entered-in-error"}
)

DATA_ABSENT_REASONS = frozenset(
    {
        "unknown",
        "asked-unknown",
        "temp-unknown",
        "not-asked",
        "asked-declined",
        "masked",
        "not-applicable",
        "unsupported",
        "as-text",
        "error",
        "not-a-number",
        "negative-infinity",
        "positive-infinity",
        "not-performed",
        "not-permitted",
    }
)


def structural_errors(bundle: dict[str, Any]) -> list[str]:
    """Every structural problem in `bundle`, as readable lines.

    A list rather than an exception: one call reports all of them, and a mapper
    change that breaks six resources should not take six runs to diagnose.
    """
    problems: list[str] = []

    if bundle.get("resourceType") != "Bundle":
        problems.append(f"resourceType is {bundle.get('resourceType')!r}, not Bundle")
    if not bundle.get("id"):
        problems.append("bundle has no id")
    if bundle.get("type") not in {"document", "collection", "searchset", "batch"}:
        problems.append(f"bundle type {bundle.get('type')!r} is not an R4 bundle type")

    entries = bundle.get("entry") or []
    if not entries:
        problems.append("bundle has no entries")

    present: set[str] = set()
    for index, entry in enumerate(entries):
        resource = entry.get("resource")
        if not isinstance(resource, dict):
            problems.append(f"entry[{index}] has no resource")
            continue
        kind = resource.get("resourceType")
        identifier = resource.get("id")
        if not kind:
            problems.append(f"entry[{index}] resource has no resourceType")
        if not identifier:
            problems.append(f"entry[{index}] {kind} has no id")
        else:
            present.add(f"{kind}/{identifier}")
            if not R4_ID.match(identifier):
                problems.append(
                    f"{kind}/{identifier} is not a valid R4 id "
                    "(A-Z a-z 0-9 - . only, 64 characters at most)"
                )
        full_url = entry.get("fullUrl")
        if not isinstance(full_url, str) or not full_url.endswith(f"/{kind}/{identifier}"):
            problems.append(
                f"entry[{index}] fullUrl {full_url!r} does not end in "
                f"{kind}/{identifier} — the bundle's relative references will "
                "not resolve against it"
            )
        elif full_url.startswith("urn:uuid:"):
            # `urn:uuid:` promises an actual lowercase UUID. These ids are
            # derived from fact ids and are not one.
            problems.append(f"entry[{index}] fullUrl uses urn:uuid: for a non-UUID id")

        problems.extend(_status_errors(resource))
        problems.extend(_coding_errors(resource, f"{kind}/{identifier}"))

    problems.extend(_reference_errors(entries, present))
    return problems


def _status_errors(resource: dict[str, Any]) -> list[str]:
    kind = resource.get("resourceType", "")
    problems: list[str] = []

    allowed = STATUS_VALUE_SETS.get(kind)
    if allowed is not None:
        status = resource.get("status")
        if status not in allowed:
            problems.append(f"{kind}.status {status!r} is outside the R4 value set")

    if kind == "Condition":
        clinical = _first_code(resource.get("clinicalStatus"))
        verification = _first_code(resource.get("verificationStatus"))
        if clinical not in CONDITION_CLINICAL:
            problems.append(f"Condition.clinicalStatus {clinical!r} is not an R4 code")
        if verification not in CONDITION_VERIFICATION:
            problems.append(
                f"Condition.verificationStatus {verification!r} is not an R4 code"
            )

    absent = resource.get("dataAbsentReason")
    if absent is not None:
        code = _first_code(absent)
        if code not in DATA_ABSENT_REASONS:
            problems.append(f"dataAbsentReason {code!r} is not an R4 code")
        if any(key.startswith("value") for key in resource):
            problems.append(
                f"{kind}/{resource.get('id')} has both a value and a dataAbsentReason"
            )

    return problems


def _coding_errors(resource: dict[str, Any], where: str) -> list[str]:
    """Every `coding` needs a system and a code.

    A code without a system is unresolvable by the receiver, which makes it
    worse than the `text`-only concept the mapper emits when it has no mapping.
    """
    problems: list[str] = []
    for path, value in _walk(resource):
        if not path.endswith("coding") or not isinstance(value, list):
            continue
        for coding in value:
            if not isinstance(coding, dict):
                problems.append(f"{where}: {path} contains a non-object")
                continue
            if not coding.get("system"):
                problems.append(f"{where}: {path} has a code with no system")
            if not coding.get("code"):
                problems.append(f"{where}: {path} has a coding with no code")
    return problems


def _reference_errors(entries: list[Any], present: set[str]) -> list[str]:
    """Every `reference` must point at a resource in this bundle.

    A dangling reference is the failure that survives every unit test and breaks
    on import into somebody else's system.
    """
    problems: list[str] = []
    for entry in entries:
        resource = entry.get("resource")
        if not isinstance(resource, dict):
            continue
        where = f"{resource.get('resourceType')}/{resource.get('id')}"
        for path, value in _walk(resource):
            if path.endswith("reference") and isinstance(value, str):
                if value.startswith(("http://", "https://", "urn:")):
                    continue
                if value not in present:
                    problems.append(f"{where}: reference {value!r} resolves to nothing")
    return problems


def _first_code(concept: Any) -> Any:
    if not isinstance(concept, dict):
        return None
    codings = concept.get("coding") or []
    if not codings or not isinstance(codings[0], dict):
        return None
    return codings[0].get("code")


def _walk(node: Any, path: str = "") -> list[tuple[str, Any]]:
    """Every (path, value) pair in a nested structure."""
    found: list[tuple[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            found.append((here, value))
            found.extend(_walk(value, here))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk(item, path))
    return found
