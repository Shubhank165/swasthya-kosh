"""Intake endpoints.

`POST /intakes/{id}/answers` is the hot path: it records one answer and returns
the updated state together with the next question, so a kiosk needs one round
trip per turn even on a poor LAN.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile, status

from app.adapters.mocks import MockOCRProvider
from app.api.deps import (
    ContentDep,
    DocumentRepoDep,
    IdempotencyDep,
    IdsDep,
    IntakeServiceDep,
    PrincipalDep,
    Role,
    SettingsDep,
    require_roles,
)
from app.api.serialisers import (
    coverage_out,
    next_step_out,
    report_out,
    snapshot_out,
)
from app.schemas.common import Acknowledgement
from app.schemas.intake import (
    CompleteOut,
    ConfirmRequest,
    CoverageOut,
    CreateIntakeRequest,
    EvidenceOut,
    IntakeSnapshotOut,
    PhysicianVerifyRequest,
    ReportOut,
    StepOut,
    SubmitAnswerRequest,
    UpdateIntakeRequest,
)
from app.services.answers import SubmittedAnswer

router = APIRouter(prefix="/intakes", tags=["intakes"])


@router.post("", response_model=IntakeSnapshotOut, status_code=status.HTTP_201_CREATED)
async def create_intake(
    body: CreateIntakeRequest,
    service: IntakeServiceDep,
    guard: IdempotencyDep,
    _: PrincipalDep,
) -> IntakeSnapshotOut:
    replay = await guard.stored()
    if replay is not None:
        return IntakeSnapshotOut.model_validate(replay.response_body)
    snapshot = await service.start(
        kiosk_id=body.kiosk_id,
        department_code=body.department_code,
        patient_id=body.patient_id,
        language=body.language,
    )
    out = snapshot_out(snapshot)
    await guard.remember(out.model_dump(mode="json"), status_code=201)
    return out


@router.get("/{intake_id}", response_model=IntakeSnapshotOut)
async def get_intake(
    intake_id: str, service: IntakeServiceDep, _: PrincipalDep
) -> IntakeSnapshotOut:
    return snapshot_out(await service.get(intake_id))


@router.patch("/{intake_id}", response_model=IntakeSnapshotOut)
async def update_intake(
    intake_id: str,
    body: UpdateIntakeRequest,
    service: IntakeServiceDep,
    _: PrincipalDep,
) -> IntakeSnapshotOut:
    """Session metadata only. Clinical facts are never written through here —
    they go through `/answers`, which is the one path that builds provenance."""
    return snapshot_out(
        await service.update_metadata(
            intake_id,
            language=body.language,
            reporter=body.reporter,
            ayurveda_enabled=body.ayurveda_enabled,
            patient_id=body.patient_id,
        )
    )


@router.post("/{intake_id}/answers", response_model=IntakeSnapshotOut)
async def submit_answer(
    intake_id: str,
    body: SubmitAnswerRequest,
    service: IntakeServiceDep,
    guard: IdempotencyDep,
    _: PrincipalDep,
) -> IntakeSnapshotOut:
    """Record one answer; return the updated state and the next question."""
    replay = await guard.stored()
    if replay is not None:
        return IntakeSnapshotOut.model_validate(replay.response_body)
    snapshot = await service.submit_answer(
        intake_id,
        SubmittedAnswer(
            concept=body.concept,
            value=body.value,
            original_expression=body.original_expression,
            original_language=body.original_language,
            source_type=body.source_type,
            reported_by=body.reported_by,
            confidence=body.confidence,
            declined=body.declined,
            segment_id=body.segment_id,
            start_ms=body.start_ms,
            end_ms=body.end_ms,
            actor=body.actor,
        ),
        expected_revision=body.expected_revision,
    )
    out = snapshot_out(snapshot)
    await guard.remember(out.model_dump(mode="json"))
    return out


@router.get("/{intake_id}/next-step", response_model=StepOut | CompleteOut)
async def next_step(
    intake_id: str, service: IntakeServiceDep, _: PrincipalDep
) -> StepOut | CompleteOut:
    return next_step_out(await service.next_step(intake_id))


@router.get("/{intake_id}/coverage", response_model=CoverageOut)
async def coverage(intake_id: str, service: IntakeServiceDep, _: PrincipalDep) -> CoverageOut:
    return coverage_out(await service.coverage(intake_id))


@router.post("/{intake_id}/documents", response_model=IntakeSnapshotOut)
async def upload_document(
    intake_id: str,
    service: IntakeServiceDep,
    documents: DocumentRepoDep,
    content: ContentDep,
    settings: SettingsDep,
    ids: IdsDep,
    _: PrincipalDep,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Query()] = "other",
) -> IntakeSnapshotOut:
    """Accept a scan and run it through OCR.

    The extraction runs inline here with the mock provider. In production this
    hands off to an async worker — the shape is the same, and the facts it
    produces enter the record as unverified either way.
    """
    payload = await file.read()
    document_id = ids.new_id("doc")
    storage_dir = settings.document_storage_dir
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_key = str(storage_dir / document_id)
    (storage_dir / document_id).write_bytes(payload)

    now = service.clock.now()
    await documents.add(
        document_id=document_id,
        intake_id=intake_id,
        kind=kind,
        content_type=file.content_type or "application/octet-stream",
        storage_key=storage_key,
        byte_size=len(payload),
        uploaded_at=now,
    )
    await service.attach_document(
        intake_id, document_id=document_id, kind=kind, uploaded_at=now
    )

    ocr = MockOCRProvider(content.concepts, id_factory=ids)
    extraction = await ocr.process(
        document_id, payload, content_type=file.content_type or "application/octet-stream"
    )
    await documents.mark_processed(
        document_id,
        processed_at=service.clock.now(),
        page_count=len(extraction.pages),
        overall_confidence=extraction.overall_confidence,
        low_confidence=extraction.low_confidence,
        kind=extraction.document_kind,
    )
    snapshot = await service.apply_document_extraction(
        intake_id,
        document_id=document_id,
        facts=extraction.facts,
        low_confidence=extraction.low_confidence,
        page_count=len(extraction.pages),
        kind=extraction.document_kind,
    )
    return snapshot_out(snapshot)


@router.post("/{intake_id}/confirm", response_model=IntakeSnapshotOut)
async def confirm(
    intake_id: str,
    body: ConfirmRequest,
    service: IntakeServiceDep,
    guard: IdempotencyDep,
    _: PrincipalDep,
) -> IntakeSnapshotOut:
    """Patient confirmation loop.

    Confirming raises certainty on the facts the patient re-affirmed. It does
    not set `physician_verified` — the two are independent, and neither implies
    the other.
    """
    replay = await guard.stored()
    if replay is not None:
        return IntakeSnapshotOut.model_validate(replay.response_body)
    snapshot = await service.confirm(intake_id, corrections=body.corrections)
    out = snapshot_out(snapshot)
    await guard.remember(out.model_dump(mode="json"))
    return out


@router.get("/{intake_id}/report", response_model=ReportOut)
async def report(intake_id: str, service: IntakeServiceDep, _: PrincipalDep) -> ReportOut:
    return report_out(await service.summary(intake_id))


@router.get("/{intake_id}/facts/{fact_id}/evidence", response_model=EvidenceOut)
async def evidence(
    intake_id: str, fact_id: str, service: IntakeServiceDep, _: PrincipalDep
) -> EvidenceOut:
    """Provenance for one fact, so a report line links to the transcript offset
    or the document region it came from."""
    return EvidenceOut.model_validate(await service.evidence_for(intake_id, fact_id))


physician_router = APIRouter(prefix="/physician", tags=["physician"])


@physician_router.post("/{intake_id}/verify", response_model=IntakeSnapshotOut)
async def physician_verify(
    intake_id: str,
    body: PhysicianVerifyRequest,
    service: IntakeServiceDep,
    principal: Annotated[object, require_roles(Role.PHYSICIAN)],
) -> IntakeSnapshotOut:
    """Physician sign-off. Physician-only, enforced by `require_roles`."""
    from app.domain.clinical.provenance import UserId

    snapshot = await service.physician_verify(
        intake_id, physician_id=UserId(body.physician_id), concepts=body.concepts
    )
    return snapshot_out(snapshot)


alerts_router = APIRouter(prefix="/alerts", tags=["alerts"])


@alerts_router.post("/{alert_id}/acknowledge", response_model=Acknowledgement)
async def acknowledge_alert(
    alert_id: str,
    service: IntakeServiceDep,
    principal: Annotated[object, require_roles(Role.TRIAGE, Role.PHYSICIAN, Role.STAFF)],
) -> Acknowledgement:
    """A human takes responsibility for an alert.

    This is the only thing that permits `POST /tickets/{id}/escalate`, and it
    records who did it. Nothing automatic can reach this endpoint.
    """
    from app.api.deps import Principal
    from app.domain.clinical.provenance import UserId

    assert isinstance(principal, Principal)
    alert = await service.acknowledge_alert(alert_id, user_id=UserId(principal.user_id))
    return Acknowledgement(
        ok=True, message=f"alert {alert.rule_id} acknowledged by {principal.user_id}"
    )


@alerts_router.post("/{alert_id}/dismiss", response_model=Acknowledgement)
async def dismiss_alert(
    alert_id: str,
    reason: Annotated[str, Query(min_length=1)],
    service: IntakeServiceDep,
    principal: Annotated[object, require_roles(Role.TRIAGE, Role.PHYSICIAN)],
) -> Acknowledgement:
    from app.api.deps import Principal
    from app.domain.clinical.provenance import UserId

    assert isinstance(principal, Principal)
    alert = await service.dismiss_alert(
        alert_id, user_id=UserId(principal.user_id), reason=reason
    )
    return Acknowledgement(ok=True, message=f"alert {alert.rule_id} dismissed")
