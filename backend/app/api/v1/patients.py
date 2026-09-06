"""Patient identity and history — §8."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.auth import RequireKioskOrStaff, RequirePatient, RequireStaff
from app.api.deps import DocumentServiceDep, IdentityServiceDep
from app.core.errors import NotFoundError
from app.domain.record import PatientRef, PatientRefType
from app.schemas.api import (
    ABHALinkRequest,
    HistoryResponse,
    PatientDocumentOut,
    ResolveRequest,
    ResolveResponse,
)
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


@router.post(
    "/me/abha",
    response_model=ResolveResponse,
    summary="Link an ABHA address to the signed-in patient",
)
async def link_abha(
    principal: RequirePatient,
    service: IdentityServiceDep,
    request: ABHALinkRequest,
) -> ResolveResponse:
    """Verify an ABHA address the patient offered — 2/3 §7.2.

    **Never mandatory, and never a gate.** A failed or unavailable lookup comes
    back `verified: false` and the intake proceeds exactly as it would have; the
    entire app works with a phone number alone (§7.3). The alternative is
    turning a patient away because a government API was down, which is not a
    trade this project makes anywhere.

    What linking buys is retrieval: a patient known here under an ABHA address
    has history to carry forward on screen 5.

    `source` is passed through verbatim. When it says `"mock"` — which it does
    today — the app is expected to say so on screen, so nobody demos a mocked
    government integration as a live one.
    """
    resolved = await service.resolve(
        PatientRef(type=PatientRefType.ABHA, value=request.abha_address),
        hospital_id=principal.hospital_id,
    )
    return ResolveResponse.model_validate(resolved.to_dict())


@router.get(
    "/me/history",
    response_model=HistoryResponse,
    summary="The signed-in patient's own prior intakes at this hospital",
)
async def my_history(
    principal: RequirePatient,
    service: IdentityServiceDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> HistoryResponse:
    """What screen 5 renders — 2/3 §5.

    **Registered before `/{ref}/history`, and that ordering is load-bearing.**
    FastAPI matches in registration order, so were this second, a request for
    `/patients/me/history` would bind `ref="me"` on the staff-only route and be
    answered — or refused — as if `me` were a patient identifier.

    **The patient comes from the session, never from the request.** There is no
    path parameter here to tamper with: `principal.patient_ref` is the peppered
    HMAC the token was issued against, so "my history" can only ever mean the
    holder of this token. That is the whole reason this is a separate route
    rather than the existing one with a different guard.

    The returning-patient screen shows these back as "our record shows X — still
    correct?" per item. That is confirmation of what the hospital already holds,
    which the patient told them; it is not OCR output and it is not an
    interpretation, so it does not run into `2/3 §8`'s rule against showing
    extracted values to a patient.
    """
    if principal.patient_ref is None:  # pragma: no cover - guarded by the role
        raise NotFoundError("this session has no patient reference")
    ref = PatientRef(type=PatientRefType.PHONE, value=principal.patient_ref)
    history = await service.history(
        ref, hospital_id=principal.hospital_id, limit=limit
    )
    return HistoryResponse.model_validate(history.to_dict())


@router.get(
    "/me/documents",
    response_model=list[PatientDocumentOut],
    summary="The signed-in patient's own uploaded documents",
)
async def my_documents(
    principal: RequirePatient,
    identity: IdentityServiceDep,
    documents: DocumentServiceDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[PatientDocumentOut]:
    """The document library behind the app's Documents tab — stage 4.

    **Registered before `/{ref}/...` for the same reason `me/history` is.**
    FastAPI matches in registration order, so were this second, a request for
    `/patients/me/documents` would bind `ref="me"` on a staff route.

    **The patient comes from the session, never from the request.** There is no
    path parameter here: the intakes are resolved from `principal.patient_ref`,
    which is the peppered HMAC the token was issued against, and the document
    query is scoped to exactly those. A caller cannot widen it, because they
    never supply the scope.

    `list_documents` on the intake router exists and is staff-only, which is
    correct for what it returns — confidence figures and everything the evidence
    panel needs. This returns strictly less (`PatientDocumentOut`), because a
    patient looking at their own scans must not be handed a machine's reading of
    them (§8).
    """
    if principal.patient_ref is None:  # pragma: no cover - guarded by the role
        raise NotFoundError("this session has no patient reference")
    ref = PatientRef(type=PatientRefType.PHONE, value=principal.patient_ref)
    history = await identity.history(
        ref, hospital_id=principal.hospital_id, limit=limit
    )
    rows = await documents.list_for_intakes(
        hospital_id=principal.hospital_id,
        intake_ids=[str(intake["intake_id"]) for intake in history.intakes],
    )

    from app.domain.record import DocumentKind, DocumentStatus

    out: list[PatientDocumentOut] = []
    for row in rows:
        url: str | None = None
        # A row with no bytes is a reading the device produced on its own; there
        # is no stored image to sign a URL for.
        if row.byte_size > 0:
            url = await documents.signed_url(
                hospital_id=principal.hospital_id, document_id=row.id
            )
        out.append(
            PatientDocumentOut(
                document_id=row.id,
                kind=DocumentKind(row.kind),
                status=DocumentStatus(row.status).value,
                page_count=row.page_count,
                rejection_reason=row.rejection_reason,
                uploaded_at=row.uploaded_at,
                processed_at=row.processed_at,
                url=url,
            )
        )
    return out


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
