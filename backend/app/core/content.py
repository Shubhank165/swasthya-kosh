"""Clinical content loading.

The domain parses mappings; this module is the only place that touches the
filesystem. Loading is strict and fails at startup, because every failure mode
here is silent at runtime: a report template missing a string renders a blank
heading, an interaction row missing its source becomes an unattributable safety
claim, and neither shows up until someone is reading the output.

The question content — pathways, screens, red-flag rules — is no longer loaded.
It lives on the Jetson, and its copy is in `stale/questionnaires/`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.config import Settings, get_settings
from app.core.errors import ContentError
from app.domain.documents.ingredients import IngredientIndex
from app.domain.documents.interactions import InteractionError, InteractionTable
from app.domain.ontology.concepts import ConceptRegistry
from app.domain.questions.loader import load_questions
from app.domain.questions.model import QuestionSet
from app.domain.report.templates import TemplateError, TemplateRegistry, TemplateSet


def _read_yaml(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except FileNotFoundError as exc:
        raise ContentError(f"clinical content file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ContentError(f"invalid YAML in {path}: {exc}") from exc


def _yaml_files(directory: Path) -> Iterator[Path]:
    if not directory.is_dir():
        raise ContentError(f"clinical content directory not found: {directory}")
    yield from sorted(directory.glob("*.yaml"))


def load_concepts(path: Path) -> ConceptRegistry:
    raw = _read_yaml(path)
    if not isinstance(raw, Mapping):
        raise ContentError(f"{path}: concept registry must be a mapping of concept id to body")
    try:
        return ConceptRegistry.from_mapping(raw)
    except ValueError as exc:
        raise ContentError(f"{path}: {exc}") from exc


def load_interactions(directory: Path) -> InteractionTable:
    """Every `rules:` list under `directory`, as one table.

    A row without a `source` fails the load, which fails startup. That is the
    intended severity: an unsourced interaction claim shown to a clinician is
    worse than no interaction checking at all, because they cannot tell which
    they are looking at.
    """
    rows: list[Mapping[str, Any]] = []
    for path in _yaml_files(directory):
        raw = _read_yaml(path)
        if not isinstance(raw, Mapping) or "rules" not in raw:
            continue
        rules = raw["rules"]
        if not isinstance(rules, list):
            raise ContentError(f"{path}: 'rules' must be a list")
        for entry in rules:
            if not isinstance(entry, Mapping):
                raise ContentError(f"{path}: each interaction row must be a mapping")
            rows.append(entry)
    try:
        return InteractionTable.from_rows(rows)
    except InteractionError as exc:
        raise ContentError(f"{directory}: {exc}") from exc


def load_ingredients(path: Path) -> IngredientIndex:
    raw = _read_yaml(path)
    if not isinstance(raw, Mapping) or "ingredients" not in raw:
        raise ContentError(f"{path}: expected a top-level 'ingredients' mapping")
    body = raw["ingredients"]
    if not isinstance(body, Mapping):
        raise ContentError(f"{path}: 'ingredients' must be a mapping")
    mapping: dict[str, list[str]] = {}
    for key, synonyms in body.items():
        if not isinstance(synonyms, list):
            raise ContentError(f"{path}: ingredient '{key}' must map to a list of names")
        mapping[str(key)] = [str(s) for s in synonyms]
    return IngredientIndex(mapping)


def load_templates(directory: Path, languages: list[str], default: str) -> TemplateRegistry:
    """One template set per configured language.

    A configured language with no file fails the load rather than falling back
    to English. A patient handed an English report they cannot read, because a
    file was missing and nothing said so, is the failure this prevents.
    """
    sets: dict[str, TemplateSet] = {}
    for language in languages:
        path = directory / language / "report.yaml"
        raw = _read_yaml(path)
        if not isinstance(raw, Mapping):
            raise ContentError(f"{path}: report template must be a mapping")
        try:
            sets[language] = TemplateSet.from_mapping(language, raw)
        except TemplateError as exc:
            raise ContentError(f"{path}: {exc}") from exc
    try:
        return TemplateRegistry(sets, default=default)
    except TemplateError as exc:
        raise ContentError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class ClinicalContent:
    """Everything loaded from `clinical/`, validated and ready to use."""

    concepts: ConceptRegistry
    interactions: InteractionTable
    ingredients: IngredientIndex
    templates: TemplateRegistry
    consent: Mapping[str, Any]
    terminology_dir: Path
    #: The question content the kiosk and the patient app both walk. Parsed and
    #: compiled here, never executed here — see clinical/questions/README.md.
    questions: QuestionSet

    def field_labels(self) -> dict[str, str]:
        """Field id -> display label, for the report builder.

        Fields with no concept are absent from this map and fall back to a
        de-underscored id. They are still printed.
        """
        return {concept.concept_id: concept.display for concept in self.concepts}

    def review_queue(self) -> tuple[str, ...]:
        """Everything an engineer authored without a clinician.

        The agenda for the AIIA mentor session. Logged as a count at startup so
        it stays visible rather than becoming a file nobody opens.
        """
        return tuple(
            f"concept `{c.concept_id}` ({c.display})" for c in self.concepts.needing_review()
        )


def load_clinical_content(settings: Settings | None = None) -> ClinicalContent:
    """Load and validate everything under `clinical/`."""
    settings = settings or get_settings()
    root = settings.clinical_content_dir
    if not root.is_dir():
        raise ContentError(f"clinical content directory not found: {root}")

    consent_raw = _read_yaml(settings.consent_dir / "consent_v1.yaml")
    if not isinstance(consent_raw, Mapping):
        raise ContentError("consent artefact must be a mapping")

    content = ClinicalContent(
        concepts=load_concepts(settings.terminology_dir / "concepts.yaml"),
        interactions=load_interactions(settings.interactions_dir),
        ingredients=load_ingredients(settings.interactions_dir / "ingredients.yaml"),
        templates=load_templates(
            settings.report_templates_dir,
            settings.report_languages,
            settings.default_report_language,
        ),
        consent=consent_raw,
        terminology_dir=settings.terminology_dir,
        questions=load_questions(
            settings.questions_dir,
            content_version=settings.content_version,
            languages=settings.question_languages,
        ),
    )
    _validate(content)
    return content


def _validate(content: ClinicalContent) -> None:
    """Cross-file checks that no single file can make on its own."""
    unmapped = sorted(
        {
            key
            for rule in content.interactions
            for key in rule.pair
            if content.ingredients.resolve(key) is None
        }
    )
    if unmapped:
        # An interaction row naming an ingredient with no entry in the name
        # table can never fire, because nothing will ever resolve to it. A
        # never-firing safety rule is worse than no rule: it looks like cover.
        raise ContentError(
            "interaction rows name ingredients absent from ingredients.yaml, so those "
            f"rows can never match: {unmapped}"
        )


@lru_cache(maxsize=1)
def get_clinical_content() -> ClinicalContent:
    """Process-wide content. Loaded once at startup."""
    return load_clinical_content()
