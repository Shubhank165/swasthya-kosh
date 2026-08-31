"""Red-flag rule definitions.

Rules live in `clinical/redflags/*.yaml`. Each carries a `clinical_source` naming
the guideline or the reviewing clinician, because the first question any AIIA
mentor will ask about an alert is "who approved this rule?" and the record has
to be able to answer.

Alert wording is fixed by `label_for`: never a disease name, never a finding
addressed to the patient.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.clinical.enums import Severity, severity_rank
from app.domain.ontology.expressions import Expression, FactSource, parse_expression


class RedFlagError(ValueError):
    """Malformed rule content. Raised at load time so CI catches it."""


#: The only wording an alert is permitted to carry outward. A red flag says a
#: human must look now; it never says what is wrong.
SAFE_LABEL = "Urgent clinical review criterion triggered"


@dataclass(frozen=True, slots=True)
class RedFlagAction:
    """What the alert asks a human to do. It never mutates the queue itself."""

    notify: str = "triage"
    #: A *hint* for the acknowledging human, never applied automatically.
    priority_hint: str | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> RedFlagAction:
        if raw is None:
            return cls()
        if not isinstance(raw, Mapping):
            raise RedFlagError("'action' must be a mapping")
        return cls(
            notify=str(raw.get("notify", "triage")),
            priority_hint=str(raw["priority_hint"]) if raw.get("priority_hint") else None,
        )


@dataclass(frozen=True, slots=True)
class RedFlagRule:
    """One deterministic criterion over the fact set."""

    rule_id: str
    severity: Severity
    criteria: Expression
    action: RedFlagAction
    clinical_source: str
    #: Clinician-facing label. Patient-facing text always uses `SAFE_LABEL`.
    label: str = SAFE_LABEL
    version: int = 1
    #: Free-text guidance for the triage nurse. Never shown to the patient.
    guidance: str | None = None
    needs_clinical_review: bool = False

    def __post_init__(self) -> None:
        if not self.clinical_source:
            raise RedFlagError(
                f"rule '{self.rule_id}' has no clinical_source; every rule must name "
                "the guideline or clinician that approved it"
            )

    def matches(self, source: FactSource) -> bool:
        return self.criteria.evaluate(source)

    def concepts(self) -> frozenset[str]:
        """Concepts the rule reads. Used to check the screen actually asks them."""
        return self.criteria.concepts()

    def patient_safe_label(self) -> str:
        return SAFE_LABEL

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> RedFlagRule:
        if "id" not in raw:
            raise RedFlagError("red-flag rule requires 'id'")
        rule_id = str(raw["id"])
        criteria_raw = raw.get("criteria")
        if not isinstance(criteria_raw, Mapping):
            raise RedFlagError(f"rule '{rule_id}': 'criteria' must be a mapping")
        severity_raw = str(raw.get("severity", Severity.HIGH.value))
        try:
            severity = Severity(severity_raw)
        except ValueError as exc:
            raise RedFlagError(f"rule '{rule_id}': unknown severity '{severity_raw}'") from exc
        try:
            criteria = parse_expression(criteria_raw)
        except ValueError as exc:
            raise RedFlagError(f"rule '{rule_id}': {exc}") from exc
        return cls(
            rule_id=rule_id,
            severity=severity,
            criteria=criteria,
            action=RedFlagAction.from_mapping(raw.get("action")),
            clinical_source=str(raw.get("clinical_source", "")),
            label=str(raw.get("label", SAFE_LABEL)),
            version=int(raw.get("version", 1)),
            guidance=str(raw["guidance"]) if raw.get("guidance") else None,
            needs_clinical_review=bool(raw.get("needs_clinical_review", False)),
        )


class RedFlagRuleSet:
    """All loaded rules, ordered most severe first."""

    def __init__(self, rules: Iterable[RedFlagRule]) -> None:
        collected: dict[str, RedFlagRule] = {}
        for rule in rules:
            if rule.rule_id in collected:
                raise RedFlagError(f"duplicate red-flag rule id '{rule.rule_id}'")
            collected[rule.rule_id] = rule
        self._rules = tuple(
            sorted(collected.values(), key=lambda r: (-severity_rank(r.severity), r.rule_id))
        )

    @classmethod
    def from_mappings(cls, raws: Iterable[Mapping[str, Any]]) -> RedFlagRuleSet:
        return cls(RedFlagRule.from_mapping(raw) for raw in raws)

    def get(self, rule_id: str) -> RedFlagRule | None:
        for rule in self._rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    def concepts(self) -> frozenset[str]:
        """Every concept any rule reads."""
        if not self._rules:
            return frozenset()
        return frozenset().union(*(r.concepts() for r in self._rules))

    def rules_needing_review(self) -> tuple[RedFlagRule, ...]:
        return tuple(r for r in self._rules if r.needs_clinical_review)

    def ids(self) -> tuple[str, ...]:
        return tuple(r.rule_id for r in self._rules)

    def __iter__(self) -> Iterator[RedFlagRule]:
        return iter(self._rules)

    def __len__(self) -> int:
        return len(self._rules)

    def as_sequence(self) -> Sequence[RedFlagRule]:
        return self._rules


def blank_rule_set() -> RedFlagRuleSet:
    """An empty rule set. Used only by tests that assert the no-rules case."""
    return RedFlagRuleSet(())


_UNSAFE_LABEL_FRAGMENTS: tuple[str, ...] = (
    "you have",
    "you are having",
    "diagnosis",
    "infarction",
    "heart attack",
    "stroke",
    "cancer",
    "appendicitis",
    "sepsis",
)


def label_is_safe(label: str) -> bool:
    """False when a label states a diagnosis or addresses the patient.

    Enforced by a safety test over every shipped rule, so a well-meaning content
    edit cannot turn an alert into a diagnosis.
    """
    lowered = label.lower()
    return not any(fragment in lowered for fragment in _UNSAFE_LABEL_FRAGMENTS)


def field_names() -> tuple[str, ...]:
    """Keys a rule YAML may declare. Used by the loader to reject typos."""
    return (
        "id",
        "severity",
        "label",
        "criteria",
        "action",
        "clinical_source",
        "version",
        "guidance",
        "needs_clinical_review",
    )


_ALLOWED_KEYS = frozenset(field_names())


def validate_keys(raw: Mapping[str, Any]) -> None:
    """Reject unknown keys. A misspelt `critera:` must not silently disable a rule."""
    unknown = set(raw) - _ALLOWED_KEYS
    if unknown:
        raise RedFlagError(f"rule '{raw.get('id', '?')}': unknown keys {sorted(unknown)}")
