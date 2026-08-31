"""Consent, document, audit, report and idempotency repositories.

Consent artefacts and audit entries are insert-only. A withdrawal writes a new
artefact that supersedes the old one; nothing edits an existing consent row,
because the point of the artefact is to prove what was shown at the time.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.idempotency import IdempotencyRecord
from app.models.clinical import (
    AuditLogEntry,
    ConsentArtefact,
    DocumentRecordRow,
    IdempotencyKeyRecord,
    ReportRecord,
)


def notice_hash(text: str) -> str:
    """Hash of the exact notice shown, so the wording can be proven later."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ConsentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        artefact_id: str,
        intake_id: str | None,
        patient_id: str | None,
        consent_version: str,
        language: str,
        notice_text: str,
        granted_purposes: list[str],
        refused_purposes: list[str],
        granting_party: str,
        granted_at: datetime,
        granting_party_name: str | None = None,
        audio_asset_id: str | None = None,
        supersedes: str | None = None,
    ) -> ConsentArtefact:
        row = ConsentArtefact(
            id=artefact_id,
            intake_id=intake_id,
            patient_id=patient_id,
            consent_version=consent_version,
            language=language,
            notice_hash=notice_hash(notice_text),
            notice_text=notice_text,
            audio_asset_id=audio_asset_id,
            granted_purposes=granted_purposes,
            refused_purposes=refused_purposes,
            granting_party=granting_party,
            granting_party_name=granting_party_name,
            granted_at=granted_at,
            supersedes=supersedes,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, artefact_id: str) -> ConsentArtefact | None:
        return await self._session.get(ConsentArtefact, artefact_id)

    async def require(self, artefact_id: str) -> ConsentArtefact:
        row = await self.get(artefact_id)
        if row is None:
            raise NotFoundError(
                f"consent artefact {artefact_id} not found", details={"consent_id": artefact_id}
            )
        return row

    async def for_intake(self, intake_id: str) -> ConsentArtefact | None:
        result = await self._session.execute(
            select(ConsentArtefact)
            .where(ConsentArtefact.intake_id == intake_id)
            .where(ConsentArtefact.withdrawn_at.is_(None))
            .order_by(ConsentArtefact.granted_at.desc())
        )
        return result.scalars().first()

    async def has_purpose(self, intake_id: str, purpose: str) -> bool:
        """Whether a purpose was actually granted for this intake.

        Used to gate raw audio retention, which is off unless the patient said
        yes to that specific purpose — not merely to the intake as a whole.
        """
        artefact = await self.for_intake(intake_id)
        return artefact is not None and purpose in (artefact.granted_purposes or [])


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        document_id: str,
        intake_id: str,
        kind: str,
        content_type: str,
        storage_key: str,
        byte_size: int,
        uploaded_at: datetime,
    ) -> DocumentRecordRow:
        row = DocumentRecordRow(
            id=document_id,
            intake_id=intake_id,
            kind=kind,
            content_type=content_type,
            storage_key=storage_key,
            byte_size=byte_size,
            uploaded_at=uploaded_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def mark_processed(
        self,
        document_id: str,
        *,
        processed_at: datetime,
        page_count: int,
        overall_confidence: float,
        low_confidence: bool,
        kind: str | None = None,
    ) -> DocumentRecordRow:
        row = await self._session.get(DocumentRecordRow, document_id)
        if row is None:
            raise NotFoundError(f"document {document_id} not found")
        row.processed = True
        row.processed_at = processed_at
        row.page_count = page_count
        row.overall_confidence = overall_confidence
        row.low_confidence = low_confidence
        if kind is not None:
            row.kind = kind
        await self._session.flush()
        return row

    async def get(self, document_id: str) -> DocumentRecordRow | None:
        return await self._session.get(DocumentRecordRow, document_id)

    async def for_intake(self, intake_id: str) -> tuple[DocumentRecordRow, ...]:
        result = await self._session.execute(
            select(DocumentRecordRow)
            .where(DocumentRecordRow.intake_id == intake_id)
            .order_by(DocumentRecordRow.uploaded_at)
        )
        return tuple(result.scalars().all())


class AuditRepository:
    """Append-only audit log. Insert is the only operation offered."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        occurred_at: datetime,
        actor_id: str,
        actor_role: str,
        action: str,
        entity_type: str,
        entity_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        reason: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self._session.add(
            AuditLogEntry(
                occurred_at=occurred_at,
                actor_id=actor_id,
                actor_role=actor_role,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                before=before,
                after=after,
                reason=reason,
                request_id=request_id,
            )
        )
        await self._session.flush()

    async def for_entity(self, entity_type: str, entity_id: str) -> tuple[AuditLogEntry, ...]:
        result = await self._session.execute(
            select(AuditLogEntry)
            .where(AuditLogEntry.entity_type == entity_type, AuditLogEntry.entity_id == entity_id)
            .order_by(AuditLogEntry.occurred_at)
        )
        return tuple(result.scalars().all())


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        report_id: str,
        intake_id: str,
        intake_revision: int,
        coverage_percentage: float,
        body: dict[str, Any],
        generated_at: datetime,
        service_date: date | None = None,
    ) -> ReportRecord:
        """Store the latest report for an intake.

        One report row per intake, regenerated as the history grows. The facts
        behind it are versioned in `clinical_facts`, so nothing is lost by
        overwriting the rendered view.
        """
        existing = await self._session.execute(
            select(ReportRecord).where(ReportRecord.intake_id == intake_id)
        )
        row = existing.scalars().first()
        if row is None:
            row = ReportRecord(
                id=report_id,
                intake_id=intake_id,
                intake_revision=intake_revision,
                coverage_percentage=coverage_percentage,
                body=body,
                generated_at=generated_at,
                service_date=service_date,
            )
            self._session.add(row)
        else:
            row.intake_revision = intake_revision
            row.coverage_percentage = coverage_percentage
            row.body = body
            row.generated_at = generated_at
        await self._session.flush()
        return row

    async def for_intake(self, intake_id: str) -> ReportRecord | None:
        result = await self._session.execute(
            select(ReportRecord).where(ReportRecord.intake_id == intake_id)
        )
        return result.scalars().first()

    async def mark_verified(
        self, intake_id: str, *, physician_id: str, verified_at: datetime
    ) -> ReportRecord:
        row = await self.for_intake(intake_id)
        if row is None:
            raise NotFoundError(f"no report for intake {intake_id}")
        row.physician_verified_by = physician_id
        row.physician_verified_at = verified_at
        await self._session.flush()
        return row


class SqlIdempotencyStore:
    """Postgres-backed idempotency store. What production runs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str, endpoint: str) -> IdempotencyRecord | None:
        row = await self._session.get(IdempotencyKeyRecord, (key, endpoint))
        if row is None:
            return None
        return IdempotencyRecord(
            key=row.key,
            endpoint=row.endpoint,
            request_fingerprint=row.request_fingerprint,
            response_body=row.response_body,
            status_code=row.status_code,
            created_at=row.created_at,
        )

    async def put(self, record: IdempotencyRecord) -> None:
        self._session.add(
            IdempotencyKeyRecord(
                key=record.key,
                endpoint=record.endpoint,
                request_fingerprint=record.request_fingerprint,
                response_body=record.response_body,
                status_code=record.status_code,
                created_at=record.created_at,
            )
        )
        await self._session.flush()
