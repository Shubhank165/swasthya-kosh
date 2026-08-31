"""Concept registry.

Maps a concept id to its display name, the section it belongs to, its synonyms
(across languages and transliterations) and any terminology codes. Built from
`clinical/terminology/concepts.yaml` by a loader outside the domain — this
module only knows how to parse an already-decoded mapping and answer questions.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.domain.clinical.enums import Section
from app.domain.clinical.provenance import ConceptRef


def normalise_token(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace.

    Deliberately conservative: it must not mangle Devanagari or IAST diacritics,
    because `"seene mein jalan"` and `"सीने में जलन"` both have to survive it.
    """
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower())
    return " ".join(cleaned.split())


@dataclass(frozen=True, slots=True)
class Concept:
    """One clinical concept in the local ontology."""

    concept_id: str
    display: str
    section: Section
    synonyms: tuple[str, ...] = field(default_factory=tuple)
    #: system -> code, e.g. {"NAMASTE": "AY-...", "ICD11-TM2": "SK..."}
    codes: Mapping[str, str] = field(default_factory=dict)
    #: Review-of-systems group this concept screens, if any.
    ros_group: str | None = None
    needs_clinical_review: bool = False

    def ref(self, system: str | None = None) -> ConceptRef:
        """A `ConceptRef` for this concept, optionally carrying one system's code."""
        if system is None:
            return ConceptRef(self.concept_id, display=self.display)
        code = self.codes.get(system)
        if code is None:
            return ConceptRef(self.concept_id, display=self.display)
        return ConceptRef(self.concept_id, system=system, code=code, display=self.display)

    @classmethod
    def from_mapping(cls, concept_id: str, raw: Mapping[str, Any]) -> Concept:
        section_raw = raw.get("section")
        if section_raw is None:
            raise ValueError(f"concept '{concept_id}' is missing 'section'")
        synonyms_raw = raw.get("synonyms", ())
        if isinstance(synonyms_raw, str) or not isinstance(synonyms_raw, Sequence):
            raise ValueError(f"concept '{concept_id}': 'synonyms' must be a list")
        codes_raw = raw.get("codes", {})
        if not isinstance(codes_raw, Mapping):
            raise ValueError(f"concept '{concept_id}': 'codes' must be a mapping")
        return cls(
            concept_id=concept_id,
            display=str(raw.get("display", concept_id.replace("_", " "))),
            section=Section(str(section_raw)),
            synonyms=tuple(str(s) for s in synonyms_raw),
            codes={str(k): str(v) for k, v in codes_raw.items()},
            ros_group=str(raw["ros_group"]) if raw.get("ros_group") else None,
            needs_clinical_review=bool(raw.get("needs_clinical_review", False)),
        )


class ConceptRegistry:
    """Immutable lookup over the concept set.

    Synonym matching here is exact-on-normalised-token only. Fuzzy matching lives
    in the terminology module, where it is explicitly scored; this registry must
    stay a dictionary so its behaviour is obvious.
    """

    def __init__(self, concepts: Iterable[Concept]) -> None:
        self._by_id: dict[str, Concept] = {}
        self._by_synonym: dict[str, str] = {}
        for concept in concepts:
            if concept.concept_id in self._by_id:
                raise ValueError(f"duplicate concept id '{concept.concept_id}'")
            self._by_id[concept.concept_id] = concept
            for token in (concept.concept_id, concept.display, *concept.synonyms):
                self._by_synonym.setdefault(normalise_token(token), concept.concept_id)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> ConceptRegistry:
        """Build from a decoded `concepts.yaml` of the form `{concept_id: {...}}`."""
        return cls(Concept.from_mapping(cid, body) for cid, body in raw.items())

    def get(self, concept_id: str) -> Concept | None:
        return self._by_id.get(concept_id)

    def require(self, concept_id: str) -> Concept:
        concept = self._by_id.get(concept_id)
        if concept is None:
            raise KeyError(f"unknown concept '{concept_id}'")
        return concept

    def ref(self, concept_id: str) -> ConceptRef:
        """A `ConceptRef` for `concept_id`, falling back to a bare ref for
        concepts not yet in the registry so an unmapped extraction is not lost."""
        concept = self._by_id.get(concept_id)
        if concept is None:
            return ConceptRef(concept_id)
        return concept.ref()

    def resolve(self, expression: str) -> Concept | None:
        """Map a spoken or typed expression to a concept by exact synonym match."""
        concept_id = self._by_synonym.get(normalise_token(expression))
        return None if concept_id is None else self._by_id[concept_id]

    def in_section(self, section: Section) -> tuple[Concept, ...]:
        return tuple(c for c in self._by_id.values() if c.section is section)

    def in_ros_group(self, group: str) -> tuple[Concept, ...]:
        return tuple(c for c in self._by_id.values() if c.ros_group == group)

    def needing_review(self) -> tuple[Concept, ...]:
        return tuple(c for c in self._by_id.values() if c.needs_clinical_review)

    def __contains__(self, concept_id: object) -> bool:
        return concept_id in self._by_id

    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self) -> Iterator[Concept]:
        return iter(self._by_id.values())
