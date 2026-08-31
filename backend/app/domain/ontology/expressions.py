"""Criteria expressions over the fact set.

One evaluator, two callers: pathway field preconditions and red-flag rules. Both
are authored as YAML by clinicians, so they must share a syntax — a Vaidya who
learns to read one can read the other.

Evaluation is total and deterministic. An unestablished concept makes a leaf
false rather than raising: a red flag that cannot be evaluated has not fired.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.domain.clinical.enums import FactStatus
from app.domain.clinical.fact import ClinicalFact
from app.domain.clinical.provenance import (
    CodedValue,
    Duration,
    Quantity,
    ScaleValue,
    TextValue,
)


class FactSource(Protocol):
    """The slice of `PatientIntakeState` an expression is allowed to see."""

    def status_of(self, concept_id: str) -> FactStatus: ...

    def fact_for(self, concept_id: str) -> ClinicalFact | None: ...

    def is_answered(self, concept_id: str) -> bool: ...


class ExpressionError(ValueError):
    """Malformed criteria. Raised at load time, never at evaluation time."""


def _token_of(fact: ClinicalFact) -> str | None:
    """The comparable string token of a fact's value, for `in` / `not_in`."""
    value = fact.value
    if value is None:
        return None
    if isinstance(value, CodedValue):
        return value.code
    if isinstance(value, TextValue):
        return value.text
    return value.render()


def _number_of(fact: ClinicalFact) -> float | None:
    """The comparable magnitude of a fact's value, for numeric operators."""
    value = fact.value
    if isinstance(value, ScaleValue):
        return float(value.value)
    if isinstance(value, Quantity | Duration):
        return float(value.magnitude)
    return None


@dataclass(frozen=True, slots=True)
class Leaf:
    """A single condition on one concept.

    Every populated operator must hold for the leaf to be true. `status`
    defaults to PRESENT when a value operator is used without one, because
    "severity >= 7" implicitly means the severity was actually reported.
    """

    concept: str
    status: FactStatus | None = None
    in_: tuple[str, ...] | None = None
    not_in: tuple[str, ...] | None = None
    gte: float | None = None
    lte: float | None = None
    gt: float | None = None
    lt: float | None = None
    answered: bool | None = None

    def _has_value_operator(self) -> bool:
        return any(
            op is not None
            for op in (self.in_, self.not_in, self.gte, self.lte, self.gt, self.lt)
        )

    def evaluate(self, source: FactSource) -> bool:
        fact = source.fact_for(self.concept)
        status = FactStatus.NOT_ASKED if fact is None else fact.status

        if self.answered is not None and source.is_answered(self.concept) is not self.answered:
            return False

        expected = self.status
        if expected is None and self._has_value_operator():
            expected = FactStatus.PRESENT
        if expected is not None and status is not expected:
            return False

        if not self._has_value_operator():
            return True
        if fact is None:
            return False

        if self.in_ is not None or self.not_in is not None:
            token = _token_of(fact)
            if token is None:
                return False
            if self.in_ is not None and token not in self.in_:
                return False
            if self.not_in is not None and token in self.not_in:
                return False

        if any(op is not None for op in (self.gte, self.lte, self.gt, self.lt)):
            number = _number_of(fact)
            if number is None:
                return False
            if self.gte is not None and not number >= self.gte:
                return False
            if self.lte is not None and not number <= self.lte:
                return False
            if self.gt is not None and not number > self.gt:
                return False
            if self.lt is not None and not number < self.lt:
                return False

        return True

    def concepts(self) -> frozenset[str]:
        return frozenset({self.concept})

    def describe(self) -> str:
        parts: list[str] = [self.concept]
        if self.status is not None:
            parts.append(f"is {self.status}")
        if self.in_ is not None:
            parts.append(f"in {list(self.in_)}")
        if self.not_in is not None:
            parts.append(f"not in {list(self.not_in)}")
        for label, op in (("≥", self.gte), ("≤", self.lte), (">", self.gt), ("<", self.lt)):
            if op is not None:
                parts.append(f"{label} {op}")
        if self.answered is not None:
            parts.append("answered" if self.answered else "unanswered")
        return " ".join(parts)


@dataclass(frozen=True, slots=True)
class All:
    """Every child must hold."""

    children: tuple[Expression, ...]

    def evaluate(self, source: FactSource) -> bool:
        return all(child.evaluate(source) for child in self.children)

    def concepts(self) -> frozenset[str]:
        if not self.children:
            return frozenset()
        return frozenset().union(*(c.concepts() for c in self.children))

    def describe(self) -> str:
        return "(" + " AND ".join(c.describe() for c in self.children) + ")"


@dataclass(frozen=True, slots=True)
class AnyOf:
    """At least one child must hold."""

    children: tuple[Expression, ...]

    def evaluate(self, source: FactSource) -> bool:
        return any(child.evaluate(source) for child in self.children)

    def concepts(self) -> frozenset[str]:
        if not self.children:
            return frozenset()
        return frozenset().union(*(c.concepts() for c in self.children))

    def describe(self) -> str:
        return "(" + " OR ".join(c.describe() for c in self.children) + ")"


@dataclass(frozen=True, slots=True)
class Not:
    """The child must not hold."""

    child: Expression

    def evaluate(self, source: FactSource) -> bool:
        return not self.child.evaluate(source)

    def concepts(self) -> frozenset[str]:
        return self.child.concepts()

    def describe(self) -> str:
        return f"NOT {self.child.describe()}"


Expression = Leaf | All | AnyOf | Not

_LEAF_KEYS = frozenset(
    {"concept", "status", "in", "not_in", "gte", "lte", "gt", "lt", "answered"}
)
_COMPOSITE_KEYS = frozenset({"all", "any", "none", "not"})


def _as_tokens(raw: object, key: str) -> tuple[str, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        raise ExpressionError(f"'{key}' must be a list of values")
    return tuple(str(item) for item in raw)


def _as_number(raw: object, key: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise ExpressionError(f"'{key}' must be a number")
    return float(raw)


def parse_expression(raw: Mapping[str, Any]) -> Expression:
    """Build an expression tree from decoded YAML. Raises on anything malformed —
    a rule that does not parse must fail the build, not fail silently at runtime."""
    if not isinstance(raw, Mapping):
        raise ExpressionError(f"expression must be a mapping, got {type(raw).__name__}")

    keys = set(raw)
    composite = keys & _COMPOSITE_KEYS
    if composite:
        if len(keys) != 1:
            raise ExpressionError(
                f"composite expression must have exactly one key, got {sorted(keys)}"
            )
        key = composite.pop()
        if key == "not":
            child = raw[key]
            if not isinstance(child, Mapping):
                raise ExpressionError("'not' takes a single expression")
            return Not(parse_expression(child))
        children_raw = raw[key]
        if not isinstance(children_raw, Sequence) or isinstance(children_raw, str | bytes):
            raise ExpressionError(f"'{key}' takes a list of expressions")
        children = tuple(parse_expression(c) for c in children_raw)
        if not children:
            raise ExpressionError(f"'{key}' must not be empty")
        if key == "all":
            return All(children)
        if key == "any":
            return AnyOf(children)
        return Not(AnyOf(children))  # none

    unknown = keys - _LEAF_KEYS
    if unknown:
        raise ExpressionError(f"unknown expression keys: {sorted(unknown)}")
    if "concept" not in raw:
        raise ExpressionError("leaf expression requires 'concept'")

    status_raw = raw.get("status")
    answered_raw = raw.get("answered")
    if answered_raw is not None and not isinstance(answered_raw, bool):
        raise ExpressionError("'answered' must be a boolean")
    try:
        status = FactStatus(status_raw) if status_raw is not None else None
    except ValueError as exc:
        raise ExpressionError(f"unknown status '{status_raw}'") from exc

    return Leaf(
        concept=str(raw["concept"]),
        status=status,
        in_=_as_tokens(raw["in"], "in") if "in" in raw else None,
        not_in=_as_tokens(raw["not_in"], "not_in") if "not_in" in raw else None,
        gte=_as_number(raw["gte"], "gte") if "gte" in raw else None,
        lte=_as_number(raw["lte"], "lte") if "lte" in raw else None,
        gt=_as_number(raw["gt"], "gt") if "gt" in raw else None,
        lt=_as_number(raw["lt"], "lt") if "lt" in raw else None,
        answered=answered_raw,
    )
