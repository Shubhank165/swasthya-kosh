"""Complaint pathways — the clinical content that decides what gets asked.

A pathway is a versioned, ordered list of fields for one presenting complaint.
It lives in `clinical/pathways/*.yaml` so a Vaidya can review it in a pull
request without reading Python. This module parses and queries it; it does not
read files.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.domain.clinical.enums import AnswerShape, Section
from app.domain.ontology.expressions import Expression, FactSource, parse_expression


class PathwayError(ValueError):
    """Malformed pathway content. Raised at load time so CI catches it."""


@dataclass(frozen=True, slots=True)
class AnswerSpec:
    """The shape of answer a field expects, and the touch options that render it."""

    shape: AnswerShape
    options: tuple[str, ...] = field(default_factory=tuple)
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    multiple: bool = False

    def __post_init__(self) -> None:
        needs_options = self.shape in {AnswerShape.SINGLE_CHOICE, AnswerShape.MULTI_CHOICE}
        if needs_options and not self.options:
            raise PathwayError(f"{self.shape} requires 'options'")
        if self.shape is AnswerShape.SCALE and (self.minimum is None or self.maximum is None):
            raise PathwayError("scale requires 'min' and 'max'")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> AnswerSpec:
        if raw is None:
            return cls(shape=AnswerShape.FREE_TEXT)
        if not isinstance(raw, Mapping):
            raise PathwayError("'answer' must be a mapping")
        shape_raw = str(raw.get("type", AnswerShape.FREE_TEXT.value))
        try:
            shape = AnswerShape(shape_raw)
        except ValueError as exc:
            raise PathwayError(f"unknown answer type '{shape_raw}'") from exc
        options_raw = raw.get("options", ())
        if isinstance(options_raw, str) or not isinstance(options_raw, Sequence):
            raise PathwayError("'options' must be a list")
        return cls(
            shape=shape,
            options=tuple(str(o) for o in options_raw),
            unit=str(raw["unit"]) if raw.get("unit") else None,
            minimum=float(raw["min"]) if raw.get("min") is not None else None,
            maximum=float(raw["max"]) if raw.get("max") is not None else None,
            multiple=shape is AnswerShape.MULTI_CHOICE,
        )


@dataclass(frozen=True, slots=True)
class PathwayField:
    """One question the pathway may ask."""

    concept: str
    required: bool = True
    answer: AnswerSpec = field(default_factory=lambda: AnswerSpec(shape=AnswerShape.FREE_TEXT))
    #: Gating condition. When it fails the field is recorded NOT_APPLICABLE.
    precondition: Expression | None = None
    #: BCP-47 tag -> question text. `en` is mandatory; it is the fallback.
    prompts: Mapping[str, str] = field(default_factory=dict)
    section: Section = Section.HPI
    priority: int = 100
    skippable: bool = True
    #: Set when the field was authored by an engineer rather than a clinician.
    #: Surfaced in docs/CLINICAL_REVIEW_QUEUE.md.
    needs_clinical_review: bool = False

    def prompt_for(self, language: str | None) -> str:
        """Question text in `language`, falling back to English, then to a
        generated phrasing. There is always a question — never an empty string."""
        if language:
            exact = self.prompts.get(language)
            if exact:
                return exact
            base = self.prompts.get(language.split("-")[0])
            if base:
                return base
        english = self.prompts.get("en")
        if english:
            return english
        return f"Please tell us about {self.concept.replace('_', ' ')}."

    def applies_to(self, source: FactSource) -> bool:
        """True when the precondition is satisfied (or there is none)."""
        return self.precondition is None or self.precondition.evaluate(source)

    def precondition_reason(self) -> str | None:
        """Human-readable failing precondition, recorded on the NOT_APPLICABLE fact."""
        return None if self.precondition is None else self.precondition.describe()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, default_section: Section) -> PathwayField:
        if "concept" not in raw:
            raise PathwayError("pathway field requires 'concept'")
        prompts_raw = raw.get("prompts", {})
        if not isinstance(prompts_raw, Mapping):
            raise PathwayError("'prompts' must be a mapping of language tag to text")
        precondition_raw = raw.get("precondition")
        precondition = (
            parse_expression(precondition_raw) if isinstance(precondition_raw, Mapping) else None
        )
        if precondition_raw is not None and precondition is None:
            raise PathwayError("'precondition' must be a mapping")
        section_raw = raw.get("section")
        return cls(
            concept=str(raw["concept"]),
            required=bool(raw.get("required", True)),
            answer=AnswerSpec.from_mapping(raw.get("answer")),
            precondition=precondition,
            prompts={str(k): str(v) for k, v in prompts_raw.items()},
            section=Section(str(section_raw)) if section_raw else default_section,
            priority=int(raw.get("priority", 100)),
            skippable=bool(raw.get("skippable", True)),
            needs_clinical_review=bool(raw.get("needs_clinical_review", False)),
        )


@dataclass(frozen=True, slots=True)
class Pathway:
    """A complaint-specific question set."""

    pathway_id: str
    version: int
    matches_concepts: tuple[str, ...]
    fields: tuple[PathwayField, ...]
    review_of_systems: tuple[str, ...] = field(default_factory=tuple)
    label: str | None = None
    clinical_source: str | None = None

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for f in self.fields:
            if f.concept in seen:
                raise PathwayError(
                    f"pathway '{self.pathway_id}' repeats concept '{f.concept}'"
                )
            seen.add(f.concept)

    @property
    def required_fields(self) -> tuple[PathwayField, ...]:
        return tuple(f for f in self.fields if f.required)

    def field_for(self, concept: str) -> PathwayField | None:
        for f in self.fields:
            if f.concept == concept:
                return f
        return None

    def fields_in(self, section: Section) -> tuple[PathwayField, ...]:
        return tuple(f for f in self.fields if f.section is section)

    def matches(self, concept_id: str) -> bool:
        return concept_id in self.matches_concepts or concept_id == self.pathway_id

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> Pathway:
        if "id" not in raw:
            raise PathwayError("pathway requires 'id'")
        pathway_id = str(raw["id"])
        fields_raw = raw.get("fields", ())
        if isinstance(fields_raw, str) or not isinstance(fields_raw, Sequence):
            raise PathwayError(f"pathway '{pathway_id}': 'fields' must be a list")
        default_section = Section(str(raw.get("section", Section.HPI.value)))
        matches_raw = raw.get("matches_concepts", ())
        if isinstance(matches_raw, str) or not isinstance(matches_raw, Sequence):
            raise PathwayError(f"pathway '{pathway_id}': 'matches_concepts' must be a list")
        ros_raw = raw.get("review_of_systems", ())
        if isinstance(ros_raw, str) or not isinstance(ros_raw, Sequence):
            raise PathwayError(f"pathway '{pathway_id}': 'review_of_systems' must be a list")
        try:
            fields = tuple(
                PathwayField.from_mapping(f, default_section=default_section) for f in fields_raw
            )
        except PathwayError as exc:
            raise PathwayError(f"pathway '{pathway_id}': {exc}") from exc
        return cls(
            pathway_id=pathway_id,
            version=int(raw.get("version", 1)),
            matches_concepts=tuple(str(c) for c in matches_raw),
            fields=fields,
            review_of_systems=tuple(str(g) for g in ros_raw),
            label=str(raw["label"]) if raw.get("label") else None,
            clinical_source=str(raw["clinical_source"]) if raw.get("clinical_source") else None,
        )


class PathwayRegistry:
    """All loaded pathways, with complaint-to-pathway resolution."""

    #: Used when the chief complaint matches no specific pathway. It must always
    #: exist: an unmatched complaint still deserves a structured history.
    FALLBACK_ID = "general_follow_up"

    def __init__(self, pathways: Iterable[Pathway]) -> None:
        self._by_id: dict[str, Pathway] = {}
        for pathway in pathways:
            if pathway.pathway_id in self._by_id:
                raise PathwayError(f"duplicate pathway id '{pathway.pathway_id}'")
            self._by_id[pathway.pathway_id] = pathway

    @classmethod
    def from_mappings(cls, raws: Iterable[Mapping[str, Any]]) -> PathwayRegistry:
        return cls(Pathway.from_mapping(raw) for raw in raws)

    def get(self, pathway_id: str) -> Pathway | None:
        return self._by_id.get(pathway_id)

    def require(self, pathway_id: str) -> Pathway:
        pathway = self._by_id.get(pathway_id)
        if pathway is None:
            raise KeyError(f"unknown pathway '{pathway_id}'")
        return pathway

    def match(self, concept_id: str) -> Pathway | None:
        """Pathway for a chief-complaint concept, or None if nothing matches.

        Resolution is deterministic: id match first, then declared
        `matches_concepts`, scanned in sorted id order so two pathways claiming
        the same concept always resolve the same way.
        """
        direct = self._by_id.get(concept_id)
        if direct is not None:
            return direct
        for pathway_id in sorted(self._by_id):
            if self._by_id[pathway_id].matches(concept_id):
                return self._by_id[pathway_id]
        return None

    def match_or_fallback(self, concept_id: str) -> Pathway:
        matched = self.match(concept_id)
        if matched is not None:
            return matched
        return self.require(self.FALLBACK_ID)

    def fields_needing_review(self) -> tuple[tuple[str, PathwayField], ...]:
        """(pathway_id, field) for every field an engineer authored without a
        clinician. This is the agenda for the AIIA mentor session."""
        return tuple(
            (pathway_id, f)
            for pathway_id in sorted(self._by_id)
            for f in self._by_id[pathway_id].fields
            if f.needs_clinical_review
        )

    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self) -> Iterator[Pathway]:
        return iter(self._by_id.values())

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_id))
