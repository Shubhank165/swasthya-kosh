"""Patient identity and history — §8."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.auth import RequireKioskOrStaff, RequireStaff
from app.api.deps import IdentityServiceDep
from app.domain.record import PatientRef, PatientRefType
from app.schemas.api import HistoryResponse, ResolveRequest, ResolveResponse
from app.services.identity import parse_ref

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post(
    "/resolve",
    response_model=ResolveResponse,
    summary="Resolve a patient reference",
)
async def resolve(
    principal: RequireKioskOrStaff,
    service: IdentityServiceDep,
    request: ResolveRequest,
) -> ResolveResponse:
    """Identify a patient — or fail to, without blocking the intake.

    ABHA is never mandatory. A failed or unavailable lookup comes back
    `verified: false` and the intake proceeds as a guest; the alternative is
    turning a patient away because a government API was down.

    The `source` field is passed through verbatim. When it says `"mock"`, the
    answer came from the mock provider and the dashboard is expected to say so
    on screen.
    """
    try:
        ref_type = PatientRefType(request.type)
    except ValueError:
        ref_type = PatientRefType.GUEST
    ref = (
        PatientRef(type=PatientRefType.GUEST)
        if ref_type is PatientRefType.GUEST
        else PatientRef(type=ref_type, value=request.value)
    )
    resolved = await service.resolve(ref, hospital_id=principal.hospital_id)
    return ResolveResponse.model_validate(resolved.to_dict())


@router.get(
    "/{ref}/history",
    response_model=HistoryResponse,
    summary="Prior intakes for this patient at this hospital",
)
async def history(
    ref: str,
    principal: RequireStaff,
    service: IdentityServiceDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> HistoryResponse:
    """Previous intakes, plus what the Jetson should pre-load.

    `carry_forward` holds only **physician-verified** conditions, medicines and
    allergies. That restriction is the point: it lets the next intake ask "our
    record shows diabetes — still correct?" instead of starting fresh, without
    letting an unverified mishearing become permanent history by being repeated
    back to the patient as established fact.

    **This hospital only.** Cross-hospital retrieval requires an ABDM consent
    artefact and is not implemented; `scope_note` says so in the response so a
    dashboard cannot imply otherwise.
    """
    result = await service.history(
        parse_ref(ref), hospital_id=principal.hospital_id, limit=limit
    )
    return HistoryResponse.model_validate(result.to_dict())
