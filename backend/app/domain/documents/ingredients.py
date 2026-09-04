"""Medicine name -> ingredient key.

Exact match after folding, and nothing else. A prescription that says
"Tab. Glycomet 500 BD" resolves to `metformin`; one that says "Glycomett"
resolves to nothing.

That is on purpose. Fuzzy matching here would let a spelling difference raise an
interaction warning against a medicine the patient is not taking, and a warning
built on a guess is worse than silence — clinicians who learn to ignore one
alert learn to ignore the next.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping

from app.domain.documents.interactions import normalise_ingredient

#: Dosage forms and strength suffixes that appear on every second prescription
#: and carry no information about which drug it is.
_NOISE_TOKENS: frozenset[str] = frozenset(
    {
        "tab",
        "tabs",
        "tablet",
        "tablets",
        "cap",
        "caps",
        "capsule",
        "capsules",
        "syp",
        "syrup",
        "susp",
        "suspension",
        "inj",
        "injection",
        "oint",
        "ointment",
        "cream",
        "drops",
        "sr",
        "xr",
        "cr",
        "er",
        "md",
        "dt",
        "forte",
        "plus",
        # Frequency, as printed on an Indian prescription. Without these,
        # "Tab. Metformin 500 BD" folds to `metformin_bd` and resolves to
        # nothing — and an unresolved name contributes nothing to the
        # interaction check, so the failure is silent and looks like safety.
        "od",
        "bd",
        "bid",
        "tds",
        "tid",
        "qid",
        "qds",
        "hs",
        "sos",
        "prn",
        "stat",
        # A unit left behind after its magnitude was stripped: "500 mg" loses
        # the 500 to `_STRENGTH` and would otherwise keep the "mg".
        "mg",
        "mcg",
        "gm",
        "ml",
        "iu",
        "unit",
        "units",
        # Duration. "Metformin 500 BD for 30 days" is one medicine.
        "for",
        "day",
        "days",
        "week",
        "weeks",
        "month",
        "months",
    }
)

#: A strength: `500`, `500mg`, `12.5`, `5ml`.
_STRENGTH = re.compile(r"^\d+(?:\.\d+)?(?:mg|mcg|g|ml|iu|units?)?$")


def strip_form(name: str) -> str:
    """Drop dosage form words and strengths, keeping the drug name."""
    tokens = [t for t in re.split(r"[\s.,/()\-]+", name.strip().lower()) if t]
    kept = [t for t in tokens if t not in _NOISE_TOKENS and not _STRENGTH.match(t)]
    return " ".join(kept) if kept else name.strip()


class IngredientIndex:
    """Synonym -> ingredient key. Built once from `clinical/interactions/`."""

    def __init__(self, mapping: Mapping[str, Iterable[str]]) -> None:
        self._by_synonym: dict[str, str] = {}
        self._keys: tuple[str, ...] = tuple(sorted(mapping))
        for key, synonyms in mapping.items():
            normalised_key = normalise_ingredient(key)
            self._by_synonym.setdefault(normalised_key, normalised_key)
            for synonym in synonyms:
                self._by_synonym.setdefault(normalise_ingredient(synonym), normalised_key)

    def resolve(self, name: str) -> str | None:
        """The ingredient key for a printed or spoken medicine name.

        Returns `None` when the name is not in the table. Callers must treat
        that as "not resolvable", never as "no interaction".
        """
        if not name or not name.strip():
            return None
        direct = self._by_synonym.get(normalise_ingredient(name))
        if direct is not None:
            return direct
        return self._by_synonym.get(normalise_ingredient(strip_form(name)))

    @property
    def keys(self) -> tuple[str, ...]:
        return self._keys

    def __len__(self) -> int:
        return len(self._by_synonym)

    def __iter__(self) -> Iterator[str]:
        return iter(self._by_synonym)


EMPTY_INDEX = IngredientIndex({})
