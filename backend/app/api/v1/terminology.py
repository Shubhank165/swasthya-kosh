"""Terminology endpoints.

Search returns candidates from every requested system side by side with their
scores, because a Vaidya coding a case needs to see the NAMASTE term and the
ICD-11 candidates together and choose — not be handed one system's answer as
though it were the answer.

Where no mapping exists, `mappings` is empty. Nothing here invents one.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import PrincipalDep, TerminologyServiceDep
from app.schemas.terminology import TerminologyMatchOut, TerminologySearchOut
from app.services.terminology import SUPPORTED_SYSTEMS

router = APIRouter(prefix="/terminology", tags=["terminology"])


@router.get("/search", response_model=TerminologySearchOut)
async def search(
    service: TerminologyServiceDep,
    _: PrincipalDep,
    q: Annotated[str, Query(min_length=1)],
    systems: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> TerminologySearchOut:
    wanted = tuple(s.strip() for s in systems.split(",")) if systems else SUPPORTED_SYSTEMS
    results = await service.search(q, systems=wanted, limit=limit)
    return TerminologySearchOut(
        query=q,
        systems=list(wanted),
        results=[
            TerminologyMatchOut(
                system=r.system,
                code=r.code,
                display=r.display,
                score=r.score,
                matched_on=r.matched_on,
                definition=r.definition,
                mappings={k: dict(v) for k, v in r.mappings.items()},
            )
            for r in results
        ],
    )


@router.get("/CodeSystem/{system}", response_model=dict)
async def code_system(
    system: str, service: TerminologyServiceDep, _: PrincipalDep
) -> dict[str, Any]:
    """FHIR R4 `CodeSystem` for one terminology."""
    return await service.code_system(system)


@router.get("/ConceptMap", response_model=dict)
async def concept_map(service: TerminologyServiceDep, _: PrincipalDep) -> dict[str, Any]:
    """FHIR R4 `ConceptMap` across NAMASTE, TM2 and MMS."""
    return await service.concept_map()


@router.get("/ValueSet/{system}", response_model=dict)
async def value_set(
    system: str, service: TerminologyServiceDep, _: PrincipalDep
) -> dict[str, Any]:
    """FHIR R4 `ValueSet` enumerating one system's codes."""
    return await service.value_set(system)


@router.get("/dual-codes", response_model=dict[str, str])
async def dual_codes(
    service: TerminologyServiceDep,
    _: PrincipalDep,
    system: Annotated[str, Query()],
    code: Annotated[str, Query()],
) -> dict[str, str]:
    """Every code equivalent to `code`, including itself.

    Where nothing maps, the result holds only the source code. That is the
    correct answer, not an incomplete one.
    """
    return dict(await service.dual_codes(system, code))
