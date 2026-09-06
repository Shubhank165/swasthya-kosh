"""The layer that stops the questionnaire — §28.

Kept away from the scoring on purpose. The selector's job is deciding what is
worth asking next; this one's is noticing that the answer to something already
asked means nobody should be asked anything else. Mixing them would make an
emergency a matter of weights.

It does not diagnose and it is not asked to. It answers one question — should
this stop and should somebody look now — and the label it produces says exactly
that and nothing about what is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.questioning_agent.core.patient_state import PatientState
from app.questioning_agent.core.schemas import RedFlag
from app.questioning_agent.knowledge.information_schema import ContentError


@dataclass(frozen=True, slots=True)
class Criterion:
    slot: str
    equals: Any = None
    any_of: tuple[str, ...] = ()
    at_least: float | None = None

    def holds(self, state: PatientState) -> bool:
        """**Unknown is not a match.** A rule fires on what a patient said."""
        if not state.knows(self.slot):
            return False
        value = state.value(self.slot)

        if self.at_least is not None:
            number = _number(value)
            return number is not None and number >= self.at_least
        if self.any_of:
            if isinstance(value, (list, tuple, set)):
                return bool(set(self.any_of) & {str(v) for v in value})
            return str(value) in self.any_of
        if self.equals is not None:
            return bool(value == self.equals)
        return True


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    severity: str
    label: str
    criteria: tuple[Criterion, ...]

    def fires(self, state: PatientState) -> bool:
        """Every criterion, and there is no `any` here on purpose.

        A rule is a conjunction. An `any` between two criteria is two rules, and
        writing them as two is what makes each one reviewable on its own line.
        """
        return all(criterion.holds(state) for criterion in self.criteria)

    def matched(self) -> tuple[str, ...]:
        return tuple(criterion.slot for criterion in self.criteria)


class TriageRules:
    def __init__(self, rules: tuple[Rule, ...]) -> None:
        self._rules = rules

    def __len__(self) -> int:
        return len(self._rules)

    def check(self, state: PatientState) -> tuple[RedFlag, ...]:
        """Every rule that fires, critical first.

        All of them, not the first: two firing rules is a more urgent case than
        one, and the desk should see both.
        """
        fired = [
            RedFlag(
                id=rule.id,
                severity=rule.severity,
                label=rule.label,
                matched=rule.matched(),
            )
            for rule in self._rules
            if rule.fires(state)
        ]
        fired.sort(key=lambda flag: (flag.severity != "critical", flag.id))
        return tuple(fired)

    @classmethod
    def load(cls, directory: Path) -> TriageRules:
        path = directory / "redflags.yaml"
        if not path.exists():
            raise ContentError(f"{path} does not exist")
        body = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(body, dict):
            raise ContentError(f"{path}: expected a mapping")

        rules: list[Rule] = []
        seen: set[str] = set()
        for entry in body.get("rules") or []:
            rule_id = str(entry.get("id") or "")
            if not rule_id:
                raise ContentError(f"{path}: a rule has no id")
            if rule_id in seen:
                raise ContentError(f"{path}: rule {rule_id!r} is defined twice")
            seen.add(rule_id)

            criteria = tuple(
                Criterion(
                    slot=str(c["slot"]),
                    equals=c.get("equals"),
                    any_of=tuple(str(v) for v in c.get("any_of") or ()),
                    at_least=c.get("at_least"),
                )
                for c in (entry.get("criteria") or {}).get("all") or ()
            )
            if not criteria:
                raise ContentError(f"{path}: rule {rule_id!r} has no criteria")

            rules.append(
                Rule(
                    id=rule_id,
                    severity=str(entry.get("severity", "high")),
                    label=str(entry["label"]),
                    criteria=criteria,
                )
            )

        if not rules:
            raise ContentError(f"{path}: no rules")
        return cls(tuple(rules))


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, dict) and "value" in value:
        inner = value["value"]
        if isinstance(inner, (int, float)) and not isinstance(inner, bool):
            return float(inner)
    return None


__all__ = ["Criterion", "Rule", "TriageRules"]
