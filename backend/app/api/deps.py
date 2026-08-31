"""FastAPI dependencies: sessions, services, auth and idempotency.

Role checking here is a header-based stand-in, wired so the endpoints that must
be physician-only genuinely are. Real authentication is a deployment concern —
the hospital's own identity provider — and the point of this shape is that
swapping it changes this file and nothing else.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.content import ClinicalContent, get_clinical_content
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.idempotency import (
    IdempotencyRecord,
    check_replay,
    fingerprint,
)
from app.core.ids import IdFactory, UuidIdFactory
from app.db import get_session
from app.events.bus import EventBus, get_event_bus
from app.repositories.alerts import AlertRepository
from app.repositories.consent import (
    AuditRepository,
    ConsentRepository,
    DocumentRepository,
    ReportRepository,
    SqlIdempotencyStore,
)
from app.repositories.intakes import IntakeRepository
from app.repositories.queues import QueueRepository
from app.repositories.terminology import TerminologyRepository
from app.services.intake import IntakeService
from app.services.queue import QueueService
from app.services.terminology import TerminologyService


class Role(StrEnum):
    """Access roles. `patient_session` is the kiosk itself, and it deliberately
    cannot reach physician endpoints."""

    PATIENT_SESSION = "patient_session"
    STAFF = "staff"
    TRIAGE = "triage"
    PHYSICIAN = "physician"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is making the request."""

    user_id: str
    role: Role

    def has_any(self, *roles: Role) -> bool:
        return self.role is Role.ADMIN or self.role in roles


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def current_principal(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> Principal:
    """Identify the caller from headers.

    A stand-in for the hospital's identity provider. It is strict about the
    role being a known one so an unrecognised value fails closed rather than
    landing somewhere permissive.
    """
    if not x_user_id or not x_user_role:
        raise UnauthorizedError("X-User-Id and X-User-Role headers are required")
    try:
        role = Role(x_user_role)
    except ValueError as exc:
        raise UnauthorizedError(f"unknown role '{x_user_role}'") from exc
    return Principal(user_id=x_user_id, role=role)


PrincipalDep = Annotated[Principal, Depends(current_principal)]


def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    """Dependency factory enforcing role membership.

    Used to make `POST /physician/{intake_id}/verify` physician-only, which is
    the one place in the API where the answer changes the clinical weight of the
    record.
    """

    def _check(principal: PrincipalDep) -> Principal:
        if not principal.has_any(*roles):
            raise ForbiddenError(
                f"role '{principal.role}' may not perform this action",
                details={"required": [r.value for r in roles]},
            )
        return principal

    return _check


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


async def get_intake_service(
    session: SessionDep,
    settings: SettingsDep,
    content: ContentDep,
    bus: BusDep,
    clock: ClockDep,
    ids: IdsDep,
) -> IntakeService:
    return IntakeService(
        intakes=IntakeRepository(session),
        alerts=AlertRepository(session),
        consent=ConsentRepository(session),
        content=content,
        bus=bus,
        settings=settings,
        clock=clock,
        ids=ids,
    )


async def get_queue_service(
    session: SessionDep,
    settings: SettingsDep,
    bus: BusDep,
    clock: ClockDep,
    ids: IdsDep,
) -> QueueService:
    return QueueService(
        queues=QueueRepository(session),
        alerts=AlertRepository(session),
        bus=bus,
        settings=settings,
        clock=clock,
        ids=ids,
    )


async def get_terminology_service(session: SessionDep) -> TerminologyService:
    return TerminologyService(TerminologyRepository(session))


async def get_document_repository(session: SessionDep) -> DocumentRepository:
    return DocumentRepository(session)


async def get_consent_repository(session: SessionDep) -> ConsentRepository:
    return ConsentRepository(session)


async def get_audit_repository(session: SessionDep) -> AuditRepository:
    return AuditRepository(session)


async def get_report_repository(session: SessionDep) -> ReportRepository:
    return ReportRepository(session)


async def get_queue_repository(session: SessionDep) -> QueueRepository:
    return QueueRepository(session)


IntakeServiceDep = Annotated[IntakeService, Depends(get_intake_service)]
QueueServiceDep = Annotated[QueueService, Depends(get_queue_service)]
TerminologyServiceDep = Annotated[TerminologyService, Depends(get_terminology_service)]
DocumentRepoDep = Annotated[DocumentRepository, Depends(get_document_repository)]
ConsentRepoDep = Annotated[ConsentRepository, Depends(get_consent_repository)]
AuditRepoDep = Annotated[AuditRepository, Depends(get_audit_repository)]
ReportRepoDep = Annotated[ReportRepository, Depends(get_report_repository)]
QueueRepoDep = Annotated[QueueRepository, Depends(get_queue_repository)]


@dataclass
class IdempotencyGuard:
    """Replay protection for one request.

    A kiosk that lost the LAN and retried must get its original response back,
    not a duplicate fact. `stored` returns the earlier response when the key and
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
        store=SqlIdempotencyStore(session),
        key=idempotency_key,
        endpoint=f"{request.method} {request.url.path}",
        payload=payload,
    )


IdempotencyDep = Annotated[IdempotencyGuard, Depends(idempotency_guard)]
