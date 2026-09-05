"""Intake ingest and read endpoints — §5, §10."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Query, status

from app.api.auth import RequireIntakeSubmitter, RequirePhysician, RequireStaff
from app.api.deps import (
    IdempotencyDep,
    IngestServiceDep,
    LabelsDep,
    ReportServiceDep,
    SettingsDep,
    idempotent,
)
from app.api.serialise import intake_out, report_out
from app.schemas.api import (
    IngestResponse,
    IntakeOut,
    ReportOut,
    VerifyRequest,
)

router = APIRouter(prefix="/intakes", tags=["intakes"])


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Receive a completed intake from a kiosk",
)
async def ingest(
    principal: RequireIntakeSubmitter,
    service: IngestServiceDep,
    guard: IdempotencyDep,
    payload: Annotated[dict[str, Any], Body()],
) -> IngestResponse:
    """Take one kiosk payload all the way to a persisted record.

    Idempotent on `Idempotency-Key`: the same key replayed returns the original
    result and creates nothing. The Jetson retries, and a hospital LAN gives it
    reason to.

    A payload that fails its contract goes to the repair path, not to a
    rejection — see §5.1. One that cannot be repaired is stored raw and comes
    back with `needs_manual_review: true` and a 200, because a device that keeps
    retrying an unparseable payload eventually drops it, and the answers are
    worth more than the status code.
    """

    async def _produce() -> IngestResponse:
        result = await service.ingest(
            payload, hospital_id=principal.hospital_id, actor_id=principal.user_id
        )
        return IngestResponse.model_validate(result.to_dict())

    return await idempotent(guard, IngestResponse, _produce)


@router.get(
    "/{intake_id}",
    response_model=IntakeOut,
    summary="The canonical record for one intake",
)
async def get_intake(
    intake_id: str,
    principal: RequireStaff,
    service: ReportServiceDep,
    labels: LabelsDep,
    settings: SettingsDep,
) -> IntakeOut:
    """Everything on the record, with contradictions recomputed."""
    record = await service.load_record(
        hospital_id=principal.hospital_id, intake_id=intake_id
    )
    return intake_out(record, labels=labels, demo=settings.demo_mode)


@router.get(
    "/{intake_id}/report",
    response_model=ReportOut,
    summary="The physician report",
)
async def get_report(
    intake_id: str,
    principal: RequireStaff,
    service: ReportServiceDep,
    settings: SettingsDep,
    language: Annotated[str | None, Query()] = None,
) -> ReportOut:
    """Build and return the report.

    Regenerated on every call rather than served from cache: a document that
    arrived after the last read changes the document section, and a physician
    reading a stale report is worse than one waiting a few hundred milliseconds.
    """
    bundle = await service.build(
        hospital_id=principal.hospital_id, intake_id=intake_id, language=language
    )
    return report_out(bundle, demo=settings.demo_mode)


@router.get(
    "/{intake_id}/facts/{fact_id}/evidence",
    summary="What one fact rests on",
)
async def get_evidence(
    intake_id: str,
    fact_id: str,
    principal: RequireStaff,
    service: ReportServiceDep,
) -> dict[str, Any]:
    """The transcript turn or document region behind a line of the report.

    This endpoint is why every fact carries a `SourceRef`. Without it the report
    is an assertion; with it, it is evidence a clinician can check in one click.
    """
    return await service.evidence_for(
        hospital_id=principal.hospital_id, intake_id=intake_id, fact_id=fact_id
    )


@router.post(
    "/{intake_id}/verify",
    response_model=ReportOut,
    summary="Physician confirms or amends the record",
)
async def verify(
    intake_id: str,
    principal: RequirePhysician,
    service: ReportServiceDep,
    settings: SettingsDep,
    request: Annotated[VerifyRequest, Body()] = VerifyRequest(),
) -> ReportOut:
    """Sign off the record, or the fields named.

    Writes new fact revisions recording who verified what and when; it does not
    edit the originals. Unsettled fields are skipped — an unresolved field with
    a physician's name on it would be a certainty increase with a signature.
    """
    bundle = await service.verify(
        hospital_id=principal.hospital_id,
        intake_id=intake_id,
        physician_id=principal.user_id,
        field_ids=request.field_ids,
        language=request.language,
    )
    return report_out(bundle, demo=settings.demo_mode)
