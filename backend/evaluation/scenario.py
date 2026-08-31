"""Scenario format and loading.

A scenario is a synthetic patient script plus the assertions that must hold when
it has been driven through the real state machine. The format is YAML so a
clinician can read a scenario and say whether it describes a real patient.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.core.errors import ContentError
from app.domain.clinical.enums import FactStatus


class ScenarioError(ValueError):
    """A malformed scenario. Fatal: a scenario that does not parse proves nothing."""


@dataclass(frozen=True, slots=True)
class ScriptedTurn:
    """One patient answer.

    `ask` names the concept the answer is for. The harness does not put the
    answer wherever the machine happens to be — it drives the machine and feeds
    the scripted answer when that concept comes up, which is what makes
    "irrelevant questions asked" a measurable number.
    """

    ask: str
    answer: Any = None
    #: The patient's verbatim words, when the scenario models a spoken answer.
    #: Only this becomes `original_expression`: stringifying a structured answer
    #: would put `{'magnitude': 2, 'unit': 'hours'}` in the report as though the
    #: patient had said it.
    said: str | None = None
    lang: str | None = None
    declined: bool = False
    source: str = "voice"
    confidence: float = 0.95


@dataclass(frozen=True, slots=True)
class ExpectedFact:
    concept: str
    status: FactStatus
    value: str | None = None


@dataclass(frozen=True, slots=True)
class Scenario:
    """One synthetic patient and everything that must be true afterwards."""

    scenario_id: str
    patient_script: tuple[ScriptedTurn, ...]
    expect_facts: tuple[ExpectedFact, ...] = field(default_factory=tuple)
    #: Concepts the machine must have asked. Drives required-field recall.
    expect_required_questions: tuple[str, ...] = field(default_factory=tuple)
    expect_red_flags: tuple[str, ...] = field(default_factory=tuple)
    #: Rules that must NOT fire. Drives the false-positive rate.
    forbid_red_flags: tuple[str, ...] = field(default_factory=tuple)
    #: Phrases that must not appear in the generated report. Target: zero hits.
    forbid_assertions: tuple[str, ...] = field(default_factory=tuple)
    expect_contradictions: tuple[str, ...] = field(default_factory=tuple)
    #: Stop after this many questions to model a patient who walked away.
    abandon_after: int | None = None
    expect_complete: bool = True
    reporter: str = "self"
    language: str = "en"
    #: Facts injected before the run — a prior record, or a scanned document.
    prior_facts: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    description: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> Scenario:
        if "id" not in raw:
            raise ScenarioError("scenario requires 'id'")
        scenario_id = str(raw["id"])
        script_raw = raw.get("patient_script", [])
        if not isinstance(script_raw, Sequence) or isinstance(script_raw, str):
            raise ScenarioError(f"{scenario_id}: 'patient_script' must be a list")

        turns: list[ScriptedTurn] = []
        for entry in script_raw:
            if not isinstance(entry, Mapping) or "ask" not in entry:
                raise ScenarioError(f"{scenario_id}: each script turn requires 'ask'")
            turns.append(
                ScriptedTurn(
                    ask=str(entry["ask"]),
                    answer=entry.get("answer"),
                    said=str(entry["said"]) if entry.get("said") else None,
                    lang=str(entry["lang"]) if entry.get("lang") else None,
                    declined=bool(entry.get("declined", False)),
                    source=str(entry.get("source", "voice")),
                    confidence=float(entry.get("confidence", 0.95)),
                )
            )

        expected: list[ExpectedFact] = []
        for entry in raw.get("expect_facts", []) or []:
            if not isinstance(entry, Mapping) or "concept" not in entry:
                raise ScenarioError(f"{scenario_id}: each expect_facts entry requires 'concept'")
            try:
                status = FactStatus(str(entry.get("status", "present")))
            except ValueError as exc:
                raise ScenarioError(
                    f"{scenario_id}: unknown status '{entry.get('status')}'"
                ) from exc
            expected.append(
                ExpectedFact(
                    concept=str(entry["concept"]),
                    status=status,
                    value=str(entry["value"]) if entry.get("value") is not None else None,
                )
            )

        def strings(key: str) -> tuple[str, ...]:
            values = raw.get(key, []) or []
            if isinstance(values, str) or not isinstance(values, Sequence):
                raise ScenarioError(f"{scenario_id}: '{key}' must be a list")
            return tuple(str(v) for v in values)

        priors = raw.get("prior_facts", []) or []
        if not isinstance(priors, Sequence) or isinstance(priors, str):
            raise ScenarioError(f"{scenario_id}: 'prior_facts' must be a list")

        return cls(
            scenario_id=scenario_id,
            patient_script=tuple(turns),
            expect_facts=tuple(expected),
            expect_required_questions=strings("expect_required_questions"),
            expect_red_flags=strings("expect_red_flags"),
            forbid_red_flags=strings("forbid_red_flags"),
            forbid_assertions=strings("forbid_assertions"),
            expect_contradictions=strings("expect_contradictions"),
            abandon_after=int(raw["abandon_after"]) if raw.get("abandon_after") else None,
            expect_complete=bool(raw.get("expect_complete", True)),
            reporter=str(raw.get("reporter", "self")),
            language=str(raw.get("language", "en")),
            prior_facts=tuple(p for p in priors if isinstance(p, Mapping)),
            description=str(raw.get("description", "")),
        )


def load_scenarios(directory: Path) -> tuple[Scenario, ...]:
    """Every `*.yaml` in `directory`, in id order.

    Sorted so the reported metrics are stable between runs: a metrics table that
    reorders itself is a metrics table nobody trusts.
    """
    if not directory.is_dir():
        raise ContentError(f"scenario directory not found: {directory}")
    scenarios: list[Scenario] = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, Mapping) and "scenarios" in raw:
            entries = raw["scenarios"]
        elif isinstance(raw, Sequence) and not isinstance(raw, str):
            entries = raw
        else:
            entries = [raw]
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ScenarioError(f"{path}: each scenario must be a mapping")
            try:
                scenarios.append(Scenario.from_mapping(entry))
            except ScenarioError as exc:
                raise ScenarioError(f"{path}: {exc}") from exc
    return tuple(sorted(scenarios, key=lambda s: s.scenario_id))
