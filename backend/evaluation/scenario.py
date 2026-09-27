"""Scenario format and loading.

A scenario is one synthetic intake — exactly the payload a kiosk would send —
plus everything that must still be true once the backend has normalised it and
built a report. YAML, so a clinician can read a scenario and say whether it
describes a real patient.

**This is a different harness from the one this replaces, and the difference is
the point.** The old scenarios were patient *scripts* driven through a state
machine that chose the next question. That machine now runs on the Jetson, so
this backend cannot measure question selection and must not report numbers that
imply it does. What it can measure is what it is actually responsible for: that
an answer arrives in the record meaning what the patient meant, that a red flag
is recorded exactly as the device raised it and never invented, and that nothing
in the rendered report asserts anything about the patient.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.domain.record import FieldStatus


class ScenarioError(ValueError):
    """A malformed scenario. Fatal: a scenario that does not parse proves nothing."""


@dataclass(frozen=True, slots=True)
class Scenario:
    """One synthetic intake and everything that must hold afterwards."""

    scenario_id: str
    description: str
    language: str
    #: The kiosk payload body, less the identifiers the harness fills in.
    payload: Mapping[str, Any]

    #: `field_id -> status` that must survive normalisation unchanged. The whole
    #: five-status vocabulary is in play: a scenario asserting `refused` is
    #: asserting that it did not arrive as `answered` or as a "no".
    expect_fields: Mapping[str, FieldStatus] = field(default_factory=dict)

    #: Rule ids the device raised. Recorded exactly — none dropped, none added.
    expect_red_flags: tuple[str, ...] = ()

    #: The patient's own words, which must still be somewhere in the record.
    #: A pipeline that keeps the coded value and loses the phrase has lost the
    #: only thing a physician can check the coding against.
    expect_verbatim: tuple[str, ...] = ()

    #: Phrases that must not appear in the rendered report. These carry over
    #: from the old scenarios unchanged and are the most valuable thing in them:
    #: they are the specific diagnoses a reader might expect a system like this
    #: to reach for, named one by one.
    forbid_assertions: tuple[str, ...] = ()


def _status(raw: object, *, scenario_id: str, field_id: str) -> FieldStatus:
    try:
        return FieldStatus(str(raw))
    except ValueError as exc:
        raise ScenarioError(
            f"{scenario_id}: field '{field_id}' expects unknown status {raw!r}; "
            f"the vocabulary is {sorted(s.value for s in FieldStatus)}"
        ) from exc


def _one(raw: Mapping[str, Any], *, source: Path) -> Scenario:
    scenario_id = str(raw.get("id") or "")
    if not scenario_id:
        raise ScenarioError(f"{source}: a scenario with no id proves nothing")
    payload = raw.get("payload")
    if not isinstance(payload, Mapping):
        raise ScenarioError(f"{scenario_id}: 'payload' must be a mapping")

    expect_fields = raw.get("expect_fields") or {}
    if not isinstance(expect_fields, Mapping):
        raise ScenarioError(f"{scenario_id}: 'expect_fields' must be a mapping")

    return Scenario(
        scenario_id=scenario_id,
        description=str(raw.get("description") or "").strip(),
        language=str(raw.get("language") or payload.get("language") or "en"),
        payload=payload,
        expect_fields={
            str(k): _status(v, scenario_id=scenario_id, field_id=str(k))
            for k, v in expect_fields.items()
        },
        expect_red_flags=tuple(str(x) for x in raw.get("expect_red_flags") or ()),
        expect_verbatim=tuple(str(x) for x in raw.get("expect_verbatim") or ()),
        forbid_assertions=tuple(str(x) for x in raw.get("forbid_assertions") or ()),
    )


def load_scenarios(directory: Path) -> tuple[Scenario, ...]:
    """Every scenario under `directory`, in a stable order.

    Sorted by file and then by the order written, so two runs on two machines
    report the same numbers against the same scenario ids. A harness whose
    output depends on directory iteration order is a harness nobody can diff.
    """
    if not directory.is_dir():
        raise ScenarioError(f"{directory}: no scenario directory")

    scenarios: list[Scenario] = []
    seen: dict[str, Path] = {}
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ScenarioError(f"{path}: expected a mapping with 'scenarios'")
        body = raw.get("scenarios")
        if not isinstance(body, Sequence) or isinstance(body, (str, bytes)):
            raise ScenarioError(f"{path}: 'scenarios' must be a list")
        for entry in body:
            if not isinstance(entry, Mapping):
                raise ScenarioError(f"{path}: each scenario must be a mapping")
            scenario = _one(entry, source=path)
            if scenario.scenario_id in seen:
                # Two scenarios with one id means one of them is silently not
                # being reported on, which is worse than either failing.
                raise ScenarioError(
                    f"{path}: scenario id {scenario.scenario_id!r} is already "
                    f"defined in {seen[scenario.scenario_id]}"
                )
            seen[scenario.scenario_id] = path
            scenarios.append(scenario)

    if not scenarios:
        raise ScenarioError(f"{directory}: no scenarios found")
    return tuple(scenarios)
