"""FastAPI dependencies: sessions, tenancy, services, idempotency.

Every service is constructed here, scoped to the caller's hospital. The tenant
context is set from the authenticated principal before any repository runs, so
the guard in `app/db/tenancy.py` has something to check against and every query
in the request carries the right scope without being told.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.queue.dispatch import DocumentDispatcher, build_dispatcher
from app.adapters.registry import Providers, build_providers
from app.api.auth import Principal, PrincipalDep
from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.content import ClinicalContent, get_clinical_content
from app.core.idempotency import IdempotencyRecord, check_replay, fingerprint
from app.core.ids import IdFactory, UuidIdFactory
from app.db import get_session
from app.db.tenancy import reset_tenant, set_tenant
from app.domain.report.builder import FieldLabels
from app.events.bus import EventBus, get_event_bus
from app.repositories.consent import (
    AuditRepository,
    ConsentRepository,
    IngestRawRepository,
    MetricsRepository,
    ReportRepository,
    SqlIdempotencyStore,
)
from app.repositories.documents import DocumentRepository
from app.repositories.intakes import IntakeRepository
from app.repositories.patients import HospitalRepository, PatientRepository
from app.repositories.terminology import TerminologyRepository
from app.services.documents import DocumentService
from app.services.identity import IdentityService
from app.services.ingest import IngestService
from app.services.reports import ReportService
from app.services.terminology import TerminologyService
from app.services.worklist import WorklistService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_settings_dep() -> Settings:
    return get_settings()


def get_content_dep() -> ClinicalContent:
    return get_clinical_content()


def get_clock() -> Clock:
    return SystemClock()


def get_ids() -> IdFactory:
    return UuidIdFactory()


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ContentDep = Annotated[ClinicalContent, Depends(get_content_dep)]
ClockDep = Annotated[Clock, Depends(get_clock)]
IdsDep = Annotated[IdFactory, Depends(get_ids)]
BusDep = Annotated[EventBus, Depends(get_event_bus)]

_providers: Providers | None = None


def get_providers(settings: SettingsDep) -> Providers:
    """The configured providers, built once per process."""
    global _providers
    if _providers is None:
        _providers = build_providers(settings)
    return _providers


def reset_providers() -> None:
    """Drop the cached providers. Used between tests."""
    global _providers
    _providers = None


ProvidersDep = Annotated[Providers, Depends(get_providers)]


async def tenant_context(principal: PrincipalDep) -> AsyncIterator[str]:
    """Put the caller's hospital in scope for the whole request.

    A `ContextVar` set here and reset in the `finally`, so it survives every
    `await` in the request and cannot leak into a concurrent one.
    """
    token = set_tenant(principal.hospital_id)
    try:
        yield principal.hospital_id
    finally:
        reset_tenant(token)


TenantDep = Annotated[str, Depends(tenant_context)]


def get_labels(content: ContentDep) -> FieldLabels:
    return FieldLabels(content.field_labels())


LabelsDep = Annotated[FieldLabels, Depends(get_labels)]


# --- services ----------------------------------------------------------------


async def get_ingest_service(
    session: SessionDep,
    settings: SettingsDep,
    providers: ProvidersDep,
    bus: BusDep,
    clock: ClockDep,
    ids: IdsDep,
    hospital_id: TenantDep,
) -> IngestService:
    return IngestService(
        intakes=IntakeRepository(session),
        raw=IngestRawRepository(session),
        audit=AuditRepository(session),
        bus=bus,
        clock=clock,
        ids=ids,
        repair_provider=providers.repair,
        repair_max_attempts=settings.repair_max_attempts,
        demo=settings.demo_mode,
    )


async def get_document_service(
    session: SessionDep,
    settings: SettingsDep,
    content: ContentDep,
    providers: ProvidersDep,
    bus: BusDep,
    clock: ClockDep,
    ids: IdsDep,
    hospital_id: TenantDep,
) -> DocumentService:
    return DocumentService(
        documents=DocumentRepository(session),
        intakes=IntakeRepository(session),
        storage=providers.storage,
        ocr=providers.ocr,
        bus=bus,
        clock=clock,
        ids=ids,
        interactions=content.interactions,
        ingredients=content.ingredients,
        confidence_floor=settings.ocr_confidence_floor,
        signed_url_ttl=settings.signed_url_ttl_seconds,
        demo=settings.demo_mode,
    )


async def get_worker_document_service(
    session: SessionDep,
    settings: SettingsDep,
    content: ContentDep,
    providers: ProvidersDep,
    bus: BusDep,
    clock: ClockDep,
    ids: IdsDep,
) -> DocumentService:
    """The same service, built without a principal.

    The Pub/Sub worker has no user and no token-derived hospital: the hospital
    comes from the message, and the handler puts it in scope itself before
    anything queries. Depending on `TenantDep` here would drag in
    authentication, and the push subscription would have to be issued a kiosk
    token — a credential that can also submit intakes, handed to a machine that
    only needs to read one document.
    """
    return DocumentService(
        documents=DocumentRepository(session),
        intakes=IntakeRepository(session),
        storage=providers.storage,
        ocr=providers.ocr,
        bus=bus,
        clock=clock,
        ids=ids,
        interactions=content.interactions,
        ingredients=content.ingredients,
        confidence_floor=settings.ocr_confidence_floor,
        signed_url_ttl=settings.signed_url_ttl_seconds,
        demo=settings.demo_mode,
    )


async def get_report_service(
    session: SessionDep,
    settings: SettingsDep,
    content: ContentDep,
    labels: LabelsDep,
    bus: BusDep,
    clock: ClockDep,
    ids: IdsDep,
    hospital_id: TenantDep,
) -> ReportService:
    return ReportService(
        intakes=IntakeRepository(session),
        documents=DocumentRepository(session),
        reports=ReportRepository(session),
        audit=AuditRepository(session),
        templates=content.templates,
        labels=labels,
        interactions=content.interactions,
        ingredients=content.ingredients,
        bus=bus,
        clock=clock,
        ids=ids,
        facility_timezone=settings.facility_timezone,
        demo=settings.demo_mode,
    )


async def get_identity_service(
    session: SessionDep,
    content: ContentDep,
    providers: ProvidersDep,
    clock: ClockDep,
    ids: IdsDep,
    hospital_id: TenantDep,
) -> IdentityService:
    return IdentityService(
        patients=PatientRepository(session),
        intakes=IntakeRepository(session),
        abha=providers.abha,
        clock=clock,
        ids=ids,
        labels=content.field_labels(),
    )


async def get_worklist_service(
    session: SessionDep,
    content: ContentDep,
    bus: BusDep,
    clock: ClockDep,
    hospital_id: TenantDep,
) -> WorklistService:
    return WorklistService(
        intakes=IntakeRepository(session),
        audit=AuditRepository(session),
        bus=bus,
        clock=clock,
        session=session,
        ingredients=content.ingredients,
    )


async def get_terminology_service(session: SessionDep) -> TerminologyService:
    return TerminologyService(TerminologyRepository(session))


async def get_consent_repository(session: SessionDep) -> ConsentRepository:
    return ConsentRepository(session)


async def get_audit_repository(session: SessionDep) -> AuditRepository:
    return AuditRepository(session)


async def get_hospital_repository(session: SessionDep) -> HospitalRepository:
    return HospitalRepository(session)


async def get_raw_repository(session: SessionDep) -> IngestRawRepository:
    return IngestRawRepository(session)


async def get_metrics_repository(session: SessionDep) -> MetricsRepository:
    return MetricsRepository(session)


IngestServiceDep = Annotated[IngestService, Depends(get_ingest_service)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
WorkerDocumentServiceDep = Annotated[DocumentService, Depends(get_worker_document_service)]

ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]
IdentityServiceDep = Annotated[IdentityService, Depends(get_identity_service)]
WorklistServiceDep = Annotated[WorklistService, Depends(get_worklist_service)]
TerminologyServiceDep = Annotated[TerminologyService, Depends(get_terminology_service)]
ConsentRepoDep = Annotated[ConsentRepository, Depends(get_consent_repository)]
AuditRepoDep = Annotated[AuditRepository, Depends(get_audit_repository)]
HospitalRepoDep = Annotated[HospitalRepository, Depends(get_hospital_repository)]
RawRepoDep = Annotated[IngestRawRepository, Depends(get_raw_repository)]
MetricsRepoDep = Annotated[MetricsRepository, Depends(get_metrics_repository)]


async def get_document_dispatcher(
    settings: SettingsDep,
    service: DocumentServiceDep,
    background: BackgroundTasks,
) -> DocumentDispatcher:
    """Where this request's OCR work goes.

    Per request, not per process: the inline dispatcher closes over this
    request's `BackgroundTasks` and its session-scoped service. The Pub/Sub one
    is cheap to construct — it reuses a process-wide publisher — so the two are
    built the same way rather than one being cached and the other not.
    """
    return build_dispatcher(settings, background=background, service=service)


DocumentDispatcherDep = Annotated[DocumentDispatcher, Depends(get_document_dispatcher)]



# --- idempotency -------------------------------------------------------------


@dataclass
class IdempotencyGuard:
    """Replay protection for one request.

    A kiosk that lost the LAN and retried must get its original response back,
    not a second intake. `stored` returns the earlier response when the key and
    body match; `remember` records the outcome of a fresh request.
    """

    store: SqlIdempotencyStore
    key: str | None
    endpoint: str
    payload: Any

    async def stored(self) -> IdempotencyRecord | None:
        if self.key is None:
            return None
        record = await self.store.get(self.key, self.endpoint)
        return check_replay(record, payload=self.payload)

    async def remember(self, body: dict[str, Any], status_code: int = 200) -> None:
        if self.key is None:
            return
        await self.store.put(
            IdempotencyRecord(
                key=self.key,
                endpoint=self.endpoint,
                request_fingerprint=fingerprint(self.payload),
                response_body=body,
                status_code=status_code,
                created_at=datetime.now(UTC),
            )
        )


async def idempotency_guard(
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AsyncIterator[IdempotencyGuard]:
    """Build the guard for the current request, reading its body once."""
    payload: Any = None
    if request.method in {"POST", "PATCH", "PUT"}:
        raw = await request.body()
        if raw:
            import json

            try:
                payload = json.loads(raw)
            except ValueError:
                payload = raw.decode("utf-8", errors="replace")
    yield IdempotencyGuard(
        store=SqlIdempotencyStore(session, hospital_id=principal.hospital_id),
        key=idempotency_key,
        endpoint=f"{request.method} {request.url.path}",
        payload=payload,
    )


IdempotencyDep = Annotated[IdempotencyGuard, Depends(idempotency_guard)]


async def idempotent[ModelT: BaseModel](
    guard: IdempotencyGuard,
    model: type[ModelT],
    produce: Callable[[], Awaitable[ModelT]],
) -> ModelT:
    """Run `produce` once per `Idempotency-Key`, replaying the stored response.

    Without a key it simply runs. With one, a retry returns the original
    response rather than performing the action twice — which is what stops a
    kiosk that lost the LAN from writing a second intake for the same patient.
    """
    replay = await guard.stored()
    if replay is not None:
        return model.model_validate(replay.response_body)
    result = await produce()
    await guard.remember(result.model_dump(mode="json"))
    return result


__all__ = [
    "AuditRepoDep",
    "BusDep",
    "ClockDep",
    "ConsentRepoDep",
    "ContentDep",
    "DocumentServiceDep",
    "HospitalRepoDep",
    "IdempotencyDep",
    "IdentityServiceDep",
    "IdsDep",
    "IngestServiceDep",
    "LabelsDep",
    "MetricsRepoDep",
    "Principal",
    "ProvidersDep",
    "RawRepoDep",
    "ReportServiceDep",
    "SessionDep",
    "SettingsDep",
    "TenantDep",
    "TerminologyServiceDep",
    "WorkerDocumentServiceDep",
    "WorklistServiceDep",
    "idempotent",
    "reset_providers",
]
