"""Terminology service.

Local and offline: NAMASTE, ICD-11 TM2 and ICD-11 MMS are seeded into the
database from `clinical/terminology/` and searched with the deterministic
trigram matcher. No external API, no network dependency, no model.

The rule that matters is what happens when there is no mapping: nothing is
returned. A ConceptMap that invents a correspondence between an Ayurvedic
nosological entity and a biomedical code is worse than an empty one, because it
looks authoritative and it will end up in someone's discharge summary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.adapters.fhir.mapper import (
    code_system_resource,
    concept_map_resource,
    value_set_resource,
)
from app.core.errors import ContentError
from app.domain.ontology.matching import ScoredCandidate, search
from app.repositories.terminology import TerminologyRepository

SUPPORTED_SYSTEMS: tuple[str, ...] = ("NAMASTE", "ICD11-TM2", "ICD11-MMS")

#: Seed file per system.
_SEED_FILES: Mapping[str, str] = {
    "NAMASTE": "namaste_seed.yaml",
    "ICD11-TM2": "icd11_tm2_seed.yaml",
    "ICD11-MMS": "icd11_mms_seed.yaml",
}


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One candidate, with the mappings that exist out of it."""

    system: str
    code: str
    display: str
    score: float
    matched_on: str
    definition: str | None = None
    #: `{target_system: {"code": ..., "equivalence": ...}}`. Empty when nothing
    #: maps — which is a real answer, not a gap to be filled in.
    mappings: Mapping[str, Mapping[str, str]] = field(default_factory=dict)


class TerminologyService:
    def __init__(self, repository: TerminologyRepository) -> None:
        self._repository = repository

    async def search(
        self, query: str, *, systems: Sequence[str] | None = None, limit: int = 10
    ) -> tuple[SearchResult, ...]:
        """Candidates from every requested system, side by side, with scores.

        Side by side is deliberate: a Vaidya coding a case wants to see the
        NAMASTE term and the ICD-11 candidates together and choose, not be handed
        one system's answer as though it were the answer.
        """
        wanted = tuple(systems) if systems else SUPPORTED_SYSTEMS
        candidates = await self._repository.candidates(systems=wanted)
        scored: tuple[ScoredCandidate, ...] = search(
            query, candidates, systems=wanted, limit=limit
        )
        results: list[SearchResult] = []
        for item in scored:
            mappings = await self._repository.mappings_for(item.system, item.code)
            results.append(
                SearchResult(
                    system=item.system,
                    code=item.code,
                    display=item.candidate.display,
                    score=item.score,
                    matched_on=item.matched_on,
                    definition=item.candidate.definition,
                    mappings={
                        m.target_system: {"code": m.target_code, "equivalence": m.equivalence}
                        for m in mappings
                    },
                )
            )
        return tuple(results)

    async def dual_codes(self, system: str, code: str) -> Mapping[str, str]:
        """Every code equivalent to `code`, including itself.

        This is what a `Condition` carries. Where no mapping exists the result
        holds only the source code — the caller writes what is true, not what
        would be convenient.
        """
        out: dict[str, str] = {system: code}
        for mapping in await self._repository.mappings_for(system, code):
            out[mapping.target_system] = mapping.target_code
        return out

    async def concept_map_for_concepts(self) -> Mapping[str, Mapping[str, str]]:
        """`{concept_id: {system: code}}` for the FHIR mapper.

        Built from the concept registry's own `codes` blocks plus the ConceptMap,
        so a concept coded in NAMASTE picks up its ICD-11 counterparts.
        """
        mappings = await self._repository.all_mappings()
        by_source: dict[tuple[str, str], dict[str, str]] = {}
        for row in mappings:
            key = (row.source_system, row.source_code)
            by_source.setdefault(key, {})[row.target_system] = row.target_code
        return {f"{system}:{code}": targets for (system, code), targets in by_source.items()}

    # --- FHIR resources -------------------------------------------------------

    async def code_system(self, system: str) -> dict[str, Any]:
        if system not in SUPPORTED_SYSTEMS:
            raise ContentError(f"unknown terminology system '{system}'")
        rows = await self._repository.concepts_in(system)
        version = rows[0].version if rows else "seed"
        return code_system_resource(
            system,
            [
                {"code": r.code, "display": r.display, "definition": r.definition}
                for r in rows
            ],
            version=version,
        )

    async def concept_map(self) -> dict[str, Any]:
        """The ConceptMap as a FHIR resource.

        The rows go to the mapper as they are stored. Grouping by source and
        target system is the mapper's job — doing it here as well meant two
        implementations of the same shape, and the one here was calling the
        other with the wrong arguments.
        """
        rows = await self._repository.all_mappings()
        return concept_map_resource(
            [
                {
                    "source_system": row.source_system,
                    "source_code": row.source_code,
                    "target_system": row.target_system,
                    "target_code": row.target_code,
                    "equivalence": row.equivalence,
                    "note": row.note,
                }
                for row in rows
            ],
            name="namaste-tm2-mms",
        )

    async def value_set(self, system: str) -> dict[str, Any]:
        rows = await self._repository.concepts_in(system)
        return value_set_resource(
            system.lower().replace("-", ""),
            system,
            [{"code": r.code, "display": r.display} for r in rows],
        )


async def seed_terminology(repository: TerminologyRepository, directory: Path) -> int:
    """Load the seed files into the database. Idempotent.

    The same loader ingests a full NAMASTE release: point it at a directory with
    the real files and the tables fill out. Nothing here is specific to the seed.
    """
    loaded = 0
    for system, filename in _SEED_FILES.items():
        path = directory / filename
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ContentError(f"{path}: terminology seed must be a mapping")
        version = str(raw.get("version", "seed"))
        for concept in raw.get("concepts", []) or []:
            await repository.upsert_concept(
                system=system,
                code=str(concept["code"]),
                display=str(concept.get("display", concept["code"])),
                definition=(
                    str(concept["definition"]) if concept.get("definition") else None
                ),
                discipline=str(concept["discipline"]) if concept.get("discipline") else None,
                synonyms=[str(s) for s in concept.get("synonyms", []) or []],
                version=version,
            )
            loaded += 1

    map_path = directory / "conceptmap.yaml"
    if map_path.exists():
        raw = yaml.safe_load(map_path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ContentError(f"{map_path}: concept map must be a mapping")
        for entry in raw.get("mappings", []) or []:
            source_code = entry.get("namaste")
            if not source_code:
                continue
            # A missing target is left missing. This is the whole point.
            for target_system, key in (("ICD11-TM2", "tm2"), ("ICD11-MMS", "mms")):
                target_code = entry.get(key)
                if not target_code:
                    continue
                await repository.upsert_mapping(
                    source_system="NAMASTE",
                    source_code=str(source_code),
                    target_system=target_system,
                    target_code=str(target_code),
                    equivalence=str(entry.get("equivalence", "relatedto")),
                    note=str(entry["note"]) if entry.get("note") else None,
                )
    return loaded
