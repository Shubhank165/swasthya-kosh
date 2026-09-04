"""Drug–drug interaction lookup.

**A table lookup, not a model.** Pairs of ingredients the patient is already
taking are checked against `clinical/interactions/`, every row of which carries a
`source` field naming where the statement came from. A row with no source does
not load.

Two deliberate limits:

- **Drug–drug only, among medicines the patient already takes.** Nothing here
  looks at what a physician might prescribe next. Presented as *"these two may
  interact — please review"*, never as a recommendation, never as a
  contraindication.
- **No herb–drug prediction.** The evidence base is thin, mostly in vitro, and
  frequently contradictory. An AYUSH product would make a herb–drug flag look
  like the headline feature, and it would be the least defensible thing in the
  build. Ayurvedic preparations are listed on the report as medicines the
  patient is taking, and the physician draws their own conclusions.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class InteractionSeverity(StrEnum):
    """How the source characterised the pair. Presentation only."""

    MAJOR = "major"
    MODERATE = "moderate"
    MINOR = "minor"


_SEVERITY_ORDER: tuple[InteractionSeverity, ...] = (
    InteractionSeverity.MINOR,
    InteractionSeverity.MODERATE,
    InteractionSeverity.MAJOR,
)


def severity_rank(severity: InteractionSeverity) -> int:
    return _SEVERITY_ORDER.index(severity)


class InteractionError(ValueError):
    """An interaction table row was malformed or unsourced."""


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalise_ingredient(name: str) -> str:
    """A comparable key for a medicine name.

    Case, punctuation, brand suffixes and Devanagari diacritics all vary between
    a printed prescription and a spoken answer. This is exact-match-after-folding
    only: fuzzy medicine matching belongs in the terminology service, where it is
    scored and shown, not buried in a safety lookup.
    """
    folded = unicodedata.normalize("NFKD", name.strip().lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return _NON_ALNUM.sub("_", folded).strip("_")


@dataclass(frozen=True, slots=True)
class InteractionRule:
    """One sourced statement about one pair of ingredients."""

    #: Normalised, and stored in sorted order so lookup is direction-free.
    pair: tuple[str, str]
    severity: InteractionSeverity
    #: What may happen. Descriptive; never an instruction.
    effect: str
    #: Where this came from. Mandatory — an unsourced interaction claim is a
    #: rumour, and this table is read by clinicians.
    source: str
    note: str | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> InteractionRule:
        try:
            left = normalise_ingredient(str(raw["a"]))
            right = normalise_ingredient(str(raw["b"]))
            effect = str(raw["effect"]).strip()
            source = str(raw["source"]).strip()
            severity = InteractionSeverity(str(raw.get("severity", "moderate")))
        except (KeyError, ValueError) as exc:
            raise InteractionError(f"invalid interaction row {dict(raw)!r}: {exc}") from exc
        if not left or not right:
            raise InteractionError("an interaction row needs two ingredient names")
        if left == right:
            raise InteractionError(f"an ingredient cannot interact with itself: {left}")
        if not effect:
            raise InteractionError(f"interaction {left}+{right} has no effect text")
        if not source:
            raise InteractionError(
                f"interaction {left}+{right} has no source; unsourced interaction "
                "claims do not load"
            )
        return cls(
            pair=tuple(sorted((left, right))),  # type: ignore[arg-type]
            severity=severity,
            effect=effect,
            source=source,
            note=str(raw["note"]) if raw.get("note") else None,
        )


@dataclass(frozen=True, slots=True)
class InteractionFinding:
    """A pair found in the patient's own medicine list."""

    rule: InteractionRule
    #: The medicine names as they appeared, so the physician sees what we matched.
    left_display: str
    right_display: str

    def render(self) -> str:
        """The report line. A request to look, not a recommendation."""
        return (
            f"{self.left_display} + {self.right_display} — "
            f"{self.rule.effect} ({self.rule.severity}). "
            f"These two may interact — please review. Source: {self.rule.source}"
        )


class InteractionTable:
    """The loaded seed table. Immutable; direction-free lookup."""

    def __init__(self, rules: Iterable[InteractionRule]) -> None:
        self._by_pair: dict[tuple[str, str], InteractionRule] = {}
        for rule in rules:
            existing = self._by_pair.get(rule.pair)
            if existing is not None and existing != rule:
                raise InteractionError(
                    f"duplicate interaction row for {rule.pair}; one pair, one statement"
                )
            self._by_pair[rule.pair] = rule

    @classmethod
    def from_rows(cls, rows: Iterable[Mapping[str, Any]]) -> InteractionTable:
        return cls(InteractionRule.from_mapping(row) for row in rows)

    def get(self, left: str, right: str) -> InteractionRule | None:
        return self._by_pair.get(tuple(sorted((left, right))))  # type: ignore[arg-type]

    def __len__(self) -> int:
        return len(self._by_pair)

    def __iter__(self) -> Iterator[InteractionRule]:
        return iter(self._by_pair.values())


@dataclass(frozen=True, slots=True)
class MedicineEntry:
    """One medicine the patient is taking, from voice or from a document."""

    display: str
    ingredient_key: str


def check(
    medicines: Sequence[MedicineEntry], table: InteractionTable
) -> tuple[InteractionFinding, ...]:
    """Every sourced pair among `medicines`, most severe first.

    Scope is exactly what §6.4 sets: drug–drug, among medicines the patient
    already takes. A medicine whose name did not resolve to an ingredient key
    contributes nothing — an unmatched name is not evidence of an interaction,
    and a guess here would be a safety claim built on a spelling.
    """
    resolved = [m for m in medicines if m.ingredient_key]
    findings: list[InteractionFinding] = []
    seen: set[tuple[str, str]] = set()
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if left.ingredient_key == right.ingredient_key:
                continue
            pair = tuple(sorted((left.ingredient_key, right.ingredient_key)))
            if pair in seen:
                continue
            rule = table.get(left.ingredient_key, right.ingredient_key)
            if rule is None:
                continue
            seen.add(pair)  # type: ignore[arg-type]
            findings.append(
                InteractionFinding(
                    rule=rule, left_display=left.display, right_display=right.display
                )
            )
    return tuple(
        sorted(
            findings,
            key=lambda f: (-severity_rank(f.rule.severity), f.left_display, f.right_display),
        )
    )
