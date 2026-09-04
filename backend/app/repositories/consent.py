"""Consent, audit, report, raw-payload and idempotency repositories.

Consent artefacts, audit entries and raw payloads are insert-only. A withdrawal
writes a new artefact that supersedes the old one; nothing edits an existing
consent row, because the point of the artefact is to prove what was shown at the
time, and a row that can be edited proves nothing.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.idempotency import IdempotencyRecord
from app.models.clinical import (
    AuditLogEntry,
    ConsentArtefact,
    IdempotencyKeyRecord,
    IngestRawRecord,
    IntakeRecord,
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
        hospital_id: str,
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
            hospital_id=hospital_id,
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

    async def get(self, *, hospital_id: str, artefact_id: str) -> ConsentArtefact | None:
        result = await self._session.execute(
            select(ConsentArtefact).where(
                ConsentArtefact.hospital_id == hospital_id,
                ConsentArtefact.id == artefact_id,
            )
        )
        return result.scalar_one_or_none()

    async def require(self, *, hospital_id: str, artefact_id: str) -> ConsentArtefact:
        row = await self.get(hospital_id=hospital_id, artefact_id=artefact_id)
        if row is None:
            raise NotFoundError(
                f"consent artefact {artefact_id} not found",
                details={"consent_id": artefact_id},
            )
        return row

    async def for_intake(
        self, *, hospital_id: str, intake_id: str
    ) -> ConsentArtefact | None:
        result = await self._session.execute(
            select(ConsentArtefact)
            .where(
                ConsentArtefact.hospital_id == hospital_id,
                ConsentArtefact.intake_id == intake_id,
                ConsentArtefact.withdrawn_at.is_(None),
            )
            .order_by(ConsentArtefact.granted_at.desc())
        )
        return result.scalars().first()

    async def has_purpose(self, *, hospital_id: str, intake_id: str, purpose: str) -> bool:
        """Whether a purpose was actually granted for this intake.

        Used to gate anything the patient must opt into specifically, rather
        than treating consent to the intake as consent to everything.
        """
        artefact = await self.for_intake(hospital_id=hospital_id, intake_id=intake_id)
        return artefact is not None and purpose in (artefact.granted_purposes or [])


class AuditRepository:
    """Append-only audit log."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def write(
        self,
        *,
        hospital_id: str,
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
    ) -> AuditLogEntry:
        row = AuditLogEntry(
            hospital_id=hospital_id,
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
        self._session.add(row)
        await self._session.flush()
        return row

    async def for_entity(
        self, *, hospital_id: str, entity_id: str, limit: int = 100
    ) -> Sequence[AuditLogEntry]:
        result = await self._session.execute(
            select(AuditLogEntry)
            .where(
                AuditLogEntry.hospital_id == hospital_id,
                AuditLogEntry.entity_id == entity_id,
            )
            .order_by(AuditLogEntry.occurred_at.desc())
            .limit(limit)
        )
        return list(result.scalars())


class ReportRepository:
    """Generated reports and their verification state."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        report_id: str,
        hospital_id: str,
        intake_id: str,
        language: str,
        template_version: str,
        body: dict[str, Any],
        generated_at: datetime,
        service_date: date | None = None,
    ) -> ReportRecord:
        """Store a report, replacing an earlier one for the same language.

        Regenerating is normal: a document arrives after ingest and the report
        changes. Physician verification is preserved across a regeneration
        rather than reset — the physician verified *facts*, and the facts they
        verified are still there.
        """
        existing = await self.get(
            hospital_id=hospital_id, intake_id=intake_id, language=language
        )
        if existing is not None:
            existing.body = body
            existing.template_version = template_version
            existing.generated_at = generated_at
            existing.service_date = service_date
            await self._session.flush()
            return existing
        row = ReportRecord(
            id=report_id,
            hospital_id=hospital_id,
            intake_id=intake_id,
            language=language,
            template_version=template_version,
            body=body,
            generated_at=generated_at,
            service_date=service_date,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(
        self, *, hospital_id: str, intake_id: str, language: str
    ) -> ReportRecord | None:
        result = await self._session.execute(
            select(ReportRecord).where(
                ReportRecord.hospital_id == hospital_id,
                ReportRecord.intake_id == intake_id,
                ReportRecord.language == language,
            )
        )
        return result.scalar_one_or_none()

    async def mark_verified(
        self, *, hospital_id: str, intake_id: str, language: str, actor_id: str, at: datetime
    ) -> ReportRecord:
        row = await self.get(
            hospital_id=hospital_id, intake_id=intake_id, language=language
        )
        if row is None:
            raise NotFoundError(f"no {language} report for intake {intake_id}")
        row.physician_verified_by = actor_id
        row.physician_verified_at = at
        await self._session.flush()
        return row


class IngestRawRepository:
    """Payloads that could not be normalised.

    **Never discard input.** A payload the parser could not handle is still
    seven minutes of a patient's answers, and the row keeps it whole so a human
    or a later normalizer can recover the intake.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store(
        self,
        *,
        record_id: str,
        hospital_id: str,
        claimed_intake_id: str | None,
        schema_version: str | None,
        reason: str,
        error_detail: dict[str, Any],
        payload: dict[str, Any],
        payload_fingerprint: str,
        repair_attempted: bool,
        received_at: datetime,
    ) -> IngestRawRecord:
        row = IngestRawRecord(
            id=record_id,
            hospital_id=hospital_id,
            claimed_intake_id=claimed_intake_id,
            schema_version=schema_version,
            reason=reason,
            error_detail=error_detail,
            payload=payload,
            payload_fingerprint=payload_fingerprint,
            repair_attempted=repair_attempted,
            received_at=received_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def pending(
        self, *, hospital_id: str, limit: int = 100
    ) -> Sequence[IngestRawRecord]:
        result = await self._session.execute(
            select(IngestRawRecord)
            .where(
                IngestRawRecord.hospital_id == hospital_id,
                IngestRawRecord.resolved_at.is_(None),
            )
            .order_by(IngestRawRecord.received_at)
            .limit(limit)
        )
        return list(result.scalars())

    async def by_fingerprint(
        self, *, hospital_id: str, fingerprint: str
    ) -> IngestRawRecord | None:
        result = await self._session.execute(
            select(IngestRawRecord).where(
                IngestRawRecord.hospital_id == hospital_id,
                IngestRawRecord.payload_fingerprint == fingerprint,
            )
        )
        return result.scalars().first()


class MetricsRepository:
    """Counters worth stating out loud.

    `repair_rate` is the one that matters: it should fall as the Jetson's
    extractor improves, and a number that moves in the right direction over a
    fortnight is a better argument than any slide.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def repair_rate(self, *, hospital_id: str) -> dict[str, float | int]:
        total_result = await self._session.execute(
            select(func.count(IntakeRecord.id)).where(
                IntakeRecord.hospital_id == hospital_id
            )
        )
        total = total_result.scalar()
        repaired_result = await self._session.execute(
            select(func.count(IntakeRecord.id)).where(
                IntakeRecord.hospital_id == hospital_id,
                IntakeRecord.repaired.is_(True),
            )
        )
        manual_result = await self._session.execute(
            select(func.count(IntakeRecord.id)).where(
                IntakeRecord.hospital_id == hospital_id,
                IntakeRecord.needs_manual_review.is_(True),
            )
        )
        repaired = int(repaired_result.scalar() or 0)
        manual = int(manual_result.scalar() or 0)
        total_int = int(total or 0)
        return {
            "intakes": total_int,
            "repaired": repaired,
            "needs_manual_review": manual,
            "repair_rate": round(repaired / total_int, 4) if total_int else 0.0,
        }


class SqlIdempotencyStore:
    """Postgres-backed idempotency records.

    Scoped to a hospital like everything else. A key is client-supplied, so
    without the scope one hospital's kiosk could — accidentally or otherwise —
    replay into another's namespace and be handed a response about a patient it
    has no business knowing exists.
    """

    def __init__(self, session: AsyncSession, *, hospital_id: str) -> None:
        self._session = session
        self._hospital_id = hospital_id

    async def get(self, key: str, endpoint: str) -> IdempotencyRecord | None:
        result = await self._session.execute(
            select(IdempotencyKeyRecord).where(
                IdempotencyKeyRecord.hospital_id == self._hospital_id,
                IdempotencyKeyRecord.key == key,
                IdempotencyKeyRecord.endpoint == endpoint,
            )
        )
        row = result.scalar_one_or_none()
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
                hospital_id=self._hospital_id,
                request_fingerprint=record.request_fingerprint,
                response_body=record.response_body,
                status_code=record.status_code,
                created_at=record.created_at,
            )
        )
        await self._session.flush()
