"""Clinical content loading.

The domain parses mappings; this module is the only place that touches the
filesystem. Loading is strict and fails at startup: a pathway that does not
parse, a red-flag rule with no `clinical_source`, a screen that asks about a
concept no rule reads — all of these stop the process rather than degrading into
a system that quietly asks fewer questions than it should.
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
from app.domain.ontology.concepts import ConceptRegistry
from app.domain.ontology.pathway import Pathway, PathwayError, PathwayRegistry
from app.domain.redflags.rules import RedFlagError, RedFlagRule, RedFlagRuleSet
from app.domain.statemachine.selectors import ContentSet


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


def load_pathway(path: Path) -> Pathway:
    raw = _read_yaml(path)
    if not isinstance(raw, Mapping):
        raise ContentError(f"{path}: pathway must be a mapping")
    try:
        return Pathway.from_mapping(raw)
    except PathwayError as exc:
        raise ContentError(f"{path}: {exc}") from exc


def load_pathway_dir(directory: Path) -> PathwayRegistry:
    """Every `*.yaml` directly inside `directory` as one registry."""
    try:
        return PathwayRegistry(load_pathway(p) for p in _yaml_files(directory))
    except PathwayError as exc:
        raise ContentError(f"{directory}: {exc}") from exc


def load_red_flags(directory: Path) -> RedFlagRuleSet:
    """Every rule in every `*.yaml` under `directory`, as one rule set.

    Each file holds a `rules:` list so related rules stay together in review.
    """
    collected: list[RedFlagRule] = []
    for path in _yaml_files(directory):
        raw = _read_yaml(path)
        if not isinstance(raw, Mapping) or "rules" not in raw:
            raise ContentError(f"{path}: red-flag file must contain a top-level 'rules' list")
        rules_raw = raw["rules"]
        if not isinstance(rules_raw, list):
            raise ContentError(f"{path}: 'rules' must be a list")
        for entry in rules_raw:
            if not isinstance(entry, Mapping):
                raise ContentError(f"{path}: each rule must be a mapping")
            try:
                collected.append(RedFlagRule.from_mapping(entry))
            except RedFlagError as exc:
                raise ContentError(f"{path}: {exc}") from exc
    try:
        return RedFlagRuleSet(collected)
    except RedFlagError as exc:
        raise ContentError(f"{directory}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ClinicalContent:
    """Everything loaded from `clinical/`, validated and ready to use."""

    concepts: ConceptRegistry
    content_set: ContentSet
    red_flags: RedFlagRuleSet
    consent: Mapping[str, Any]
    terminology_dir: Path

    @property
    def pathways(self) -> PathwayRegistry:
        return self.content_set.complaint_pathways

    def review_queue(self) -> tuple[str, ...]:
        """Everything an engineer authored without a clinician, as review lines.

        `docs/CLINICAL_REVIEW_QUEUE.md` is generated from this, and it is the
        agenda for the AIIA mentor session.
        """
        lines: list[str] = []
        lines.extend(
            f"concept `{c.concept_id}` ({c.display})" for c in self.concepts.needing_review()
        )
        lines.extend(
            f"pathway `{pathway_id}` field `{f.concept}`"
            for pathway_id, f in self.pathways.fields_needing_review()
        )
        lines.extend(
            f"pathway `{pathway_id}` field `{f.concept}`"
            for pathway_id, f in self.content_set.red_flag_screens.fields_needing_review()
        )
        lines.extend(
            f"red-flag rule `{r.rule_id}`" for r in self.red_flags.rules_needing_review()
        )
        lines.extend(
            f"red-flag rule `{r.rule_id}` has an unreviewed clinical_source: "
            f"{r.clinical_source}"
            for r in self.red_flags
            if "pending" in r.clinical_source.lower() and not r.needs_clinical_review
        )
        return tuple(lines)

    def unscreened_rule_concepts(self) -> tuple[str, ...]:
        """Concepts a red-flag rule reads that no screen or pathway ever asks.

        Such a rule can never fire. `tests/safety/` fails the build on a non-empty
        result, because a silent never-firing safety rule is worse than no rule.
        """
        asked: set[str] = {f.concept for f in self.content_set.core.fields}
        for registry in (
            self.content_set.complaint_pathways,
            self.content_set.red_flag_screens,
            self.content_set.review_of_systems,
        ):
            for pathway in registry:
                asked.update(f.concept for f in pathway.fields)
        if self.content_set.ayurveda is not None:
            asked.update(f.concept for f in self.content_set.ayurveda.fields)
        # Complaint anchors are recorded from the chief-complaint answer rather
        # than asked as their own field, so they count as screened.
        asked.update(self.content_set.complaint_pathways.ids())
        return tuple(sorted(self.red_flags.concepts() - asked))


def load_clinical_content(settings: Settings | None = None) -> ClinicalContent:
    """Load and validate everything under `clinical/`."""
    settings = settings or get_settings()
    root = settings.clinical_content_dir
    if not root.is_dir():
        raise ContentError(f"clinical content directory not found: {root}")

    concepts = load_concepts(settings.terminology_dir / "concepts.yaml")
    core = load_pathway(settings.pathways_dir / "core_intake.yaml")
    complaint_pathways = load_pathway_dir(settings.pathways_dir)
    screens = load_pathway_dir(settings.pathways_dir / "screens")
    ros = load_pathway_dir(settings.pathways_dir / "ros")
    ayurveda = (
        load_pathway(settings.ayurveda_dir / "ayurveda_module.yaml")
        if settings.ayurveda_module_enabled
        else None
    )
    red_flags = load_red_flags(settings.redflags_dir)
    consent_raw = _read_yaml(settings.consent_dir / "consent_v1.yaml")
    if not isinstance(consent_raw, Mapping):
        raise ContentError("consent artefact must be a mapping")

    content_set = ContentSet(
        core=core,
        complaint_pathways=complaint_pathways,
        red_flag_screens=screens,
        review_of_systems=ros,
        ayurveda=ayurveda,
    )
    content = ClinicalContent(
        concepts=concepts,
        content_set=content_set,
        red_flags=red_flags,
        consent=consent_raw,
        terminology_dir=settings.terminology_dir,
    )
    _validate(content)
    return content


def _validate(content: ClinicalContent) -> None:
    """Cross-file checks that no single file can make on its own."""
    if content.content_set.complaint_pathways.get(PathwayRegistry.FALLBACK_ID) is None:
        raise ContentError(
            f"the fallback pathway '{PathwayRegistry.FALLBACK_ID}' is missing; every "
            "unmatched complaint still needs a structured history"
        )
    if content.content_set.red_flag_screens.get("general") is None:
        raise ContentError("the default red-flag screen 'general' is missing")

    unknown_concepts = sorted(
        {
            f.concept
            for pathway in (
                content.content_set.core,
                *content.content_set.complaint_pathways,
                *content.content_set.red_flag_screens,
                *content.content_set.review_of_systems,
                *([content.content_set.ayurveda] if content.content_set.ayurveda else []),
            )
            for f in pathway.fields
            if f.concept not in content.concepts
        }
    )
    if unknown_concepts:
        raise ContentError(
            f"pathway fields reference concepts absent from the registry: {unknown_concepts}"
        )

    unscreened = content.unscreened_rule_concepts()
    if unscreened:
        raise ContentError(
            "red-flag rules read concepts that no screen or pathway ever asks, so those "
            f"rules can never fire: {list(unscreened)}"
        )


@lru_cache(maxsize=1)
def get_clinical_content() -> ClinicalContent:
    """Process-wide content. Loaded once at startup."""
    return load_clinical_content()
