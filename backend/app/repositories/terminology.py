"""Terminology repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ontology.matching import Candidate
from app.models.clinical import TerminologyConcept, TerminologyMapping


class TerminologyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def candidates(self, *, systems: tuple[str, ...] | None = None) -> tuple[Candidate, ...]:
        stmt = select(TerminologyConcept).order_by(
            TerminologyConcept.system, TerminologyConcept.code
        )
        if systems:
            stmt = stmt.where(TerminologyConcept.system.in_(systems))
        result = await self._session.execute(stmt)
        return tuple(
            Candidate(
                code=row.code,
                display=row.display,
                system=row.system,
                synonyms=tuple(row.synonyms or ()),
                definition=row.definition,
            )
            for row in result.scalars().all()
        )

    async def concepts_in(self, system: str) -> tuple[TerminologyConcept, ...]:
        result = await self._session.execute(
            select(TerminologyConcept)
            .where(TerminologyConcept.system == system)
            .order_by(TerminologyConcept.code)
        )
        return tuple(result.scalars().all())

    async def mappings_for(self, system: str, code: str) -> tuple[TerminologyMapping, ...]:
        """Mappings out of one code. Empty is a valid, meaningful answer."""
        result = await self._session.execute(
            select(TerminologyMapping).where(
                TerminologyMapping.source_system == system,
                TerminologyMapping.source_code == code,
            )
        )
        return tuple(result.scalars().all())

    async def all_mappings(self) -> tuple[TerminologyMapping, ...]:
        result = await self._session.execute(
            select(TerminologyMapping).order_by(
                TerminologyMapping.source_system, TerminologyMapping.source_code
            )
        )
        return tuple(result.scalars().all())

    async def upsert_concept(
        self,
        *,
        system: str,
        code: str,
        display: str,
        definition: str | None = None,
        discipline: str | None = None,
        synonyms: list[str] | None = None,
        version: str = "seed",
    ) -> None:
        existing = await self._session.execute(
            select(TerminologyConcept).where(
                TerminologyConcept.system == system, TerminologyConcept.code == code
            )
        )
        row = existing.scalars().first()
        if row is None:
            self._session.add(
                TerminologyConcept(
                    system=system,
                    code=code,
                    display=display,
                    definition=definition,
                    discipline=discipline,
                    synonyms=synonyms or [],
                    version=version,
                )
            )
        else:
            row.display = display
            row.definition = definition
            row.discipline = discipline
            row.synonyms = synonyms or []
            row.version = version
        await self._session.flush()

    async def upsert_mapping(
        self,
        *,
        source_system: str,
        source_code: str,
        target_system: str,
        target_code: str,
        equivalence: str,
        note: str | None = None,
    ) -> None:
        existing = await self._session.execute(
            select(TerminologyMapping).where(
                TerminologyMapping.source_system == source_system,
                TerminologyMapping.source_code == source_code,
                TerminologyMapping.target_system == target_system,
                TerminologyMapping.target_code == target_code,
            )
        )
        row = existing.scalars().first()
        if row is None:
            self._session.add(
                TerminologyMapping(
                    source_system=source_system,
                    source_code=source_code,
                    target_system=target_system,
                    target_code=target_code,
                    equivalence=equivalence,
                    note=note,
                )
            )
        else:
            row.equivalence = equivalence
            row.note = note
        await self._session.flush()
