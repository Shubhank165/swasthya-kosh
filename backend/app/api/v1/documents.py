"""Document upload, on-device results, and content serving — §6."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.auth import RequireKioskOrStaff, RequireStaff
from app.api.deps import DocumentDispatcherDep, DocumentServiceDep, SettingsDep
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.domain.documents.extraction import DocumentExtraction
from app.domain.record import DocumentKind
from app.schemas.api import DocumentOut, DocumentResultsRequest, DocumentUploadResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/intakes", tags=["documents"])
content_router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/{intake_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document image for OCR",
)
async def upload_document(
    intake_id: str,
    principal: RequireKioskOrStaff,
    service: DocumentServiceDep,
    dispatcher: DocumentDispatcherDep,
    file: Annotated[UploadFile, File()],
    kind: Annotated[DocumentKind, Form()] = DocumentKind.OTHER,
) -> DocumentUploadResponse:
    """Store the image and queue it for reading.

    **202, always.** Processing is asynchronous and nothing about the patient's
    experience waits on a model — they have already answered the questions, and
    the doctor sees the document section fill in when it fills in.

    Where the work goes is `DOCUMENT_QUEUE`: a background task in this process
    locally, so `docker compose up` is a complete pipeline with no broker; a
    Pub/Sub message to a separate Cloud Run worker in the cloud. Both end at the
    same `DocumentService.process`.

    The dispatch is awaited and its failure is *not* swallowed. Storing a
    photograph and then failing to queue it would leave a document that the
    physician is never shown and never told about; the kiosk is better off
    seeing the upload fail and sending it again.
    """
    content = await file.read()
    result = await service.upload(
        hospital_id=principal.hospital_id,
        intake_id=intake_id,
        content=content,
        content_type=file.content_type or "application/octet-stream",
        kind=kind,
    )
    await dispatcher.dispatch(
        hospital_id=principal.hospital_id,
        intake_id=intake_id,
        document_id=result.document_id,
    )
    return DocumentUploadResponse(
        document_id=result.document_id, status=result.status, demo=result.demo
    )


@router.post(
    "/{intake_id}/documents/results",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Accept an OCR result produced on the device",
)
async def accept_results(
    intake_id: str,
    principal: RequireKioskOrStaff,
    service: DocumentServiceDep,
    request: DocumentResultsRequest,
) -> DocumentOut:
    """Take an extraction the Jetson produced on-device.

    PP-OCRv5 Devanagari is 7.5 MB and Surya fits in 1.47 GB, so on-device OCR is
    viable — and a hospital may prefer that a photographed prescription never
    leaves the building. The image stays there; only the structured result
    crosses the network, and everything downstream is identical to the cloud
    path.

    The redaction pass runs on this input too. An extraction is not trusted
    because it came from our own device.
    """
    extraction = DocumentExtraction.model_validate(
        {**request.extraction, "kind": request.extraction.get("kind", request.kind.value)}
    )
    result = await service.accept_results(
        hospital_id=principal.hospital_id, intake_id=intake_id, extraction=extraction
    )
    return DocumentOut(
        document_id=result.document_id,
        kind=result.kind,
        status="rejected_quality" if result.was_rejected else "processed",
        page_count=result.page_count,
        confidence=result.overall_confidence,
        low_confidence=result.low_confidence,
        rejection_reason=result.quality_reason,
    )


@router.get(
    "/{intake_id}/documents",
    response_model=list[DocumentOut],
    summary="Documents attached to an intake",
)
async def list_documents(
    intake_id: str,
    principal: RequireStaff,
    service: DocumentServiceDep,
) -> list[DocumentOut]:
    """Each with a short-lived signed URL."""
    from app.domain.record import DocumentStatus

    rows = await service.list_for_intake(
        hospital_id=principal.hospital_id, intake_id=intake_id
    )
    out: list[DocumentOut] = []
    for row in rows:
        url: str | None = None
        if row.byte_size > 0:
            url = await service.signed_url(
                hospital_id=principal.hospital_id, document_id=row.id
            )
        out.append(
            DocumentOut(
                document_id=row.id,
                kind=DocumentKind(row.kind),
                status=DocumentStatus(row.status).value,
                page_count=row.page_count,
                confidence=row.overall_confidence,
                low_confidence=row.low_confidence,
                rejection_reason=row.rejection_reason,
                uploaded_at=row.uploaded_at,
                processed_at=row.processed_at,
                url=url,
            )
        )
    return out


@content_router.get(
    "/content/{key:path}",
    summary="Serve a stored document image (local storage backend only)",
)
async def document_content(
    key: str,
    principal: RequireStaff,
    service: DocumentServiceDep,
    settings: SettingsDep,
    expires: Annotated[int | None, Query()] = None,
) -> Response:
    """Serve an image from the local store.

    Exists only so the laptop demo has working evidence links. The key is
    prefixed with the hospital id, and this check is what makes the prefix
    load-bearing rather than decorative: a caller cannot read another hospital's
    object by knowing its key.

    In the deployed profile GCS signs the URL and this route is never called.
    """
    if settings.storage_backend != "local":
        raise NotFoundError("document content is served by object storage in this profile")
    data = await service.content(hospital_id=principal.hospital_id, key=key)
    media_type = "image/png" if key.endswith(".png") else "image/jpeg"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "no-store, private"},
    )
