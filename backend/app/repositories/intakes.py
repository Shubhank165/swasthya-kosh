"""Intake persistence.

Every method takes `hospital_id` and every statement filters on it. That is
belt-and-braces with the guard in `app/db/tenancy.py`: the guard catches the
query that forgot, and this is the code that does not forget.

Facts are inserted, never updated. A correction is a new row whose `supersedes`
points at the old, so `seq` is monotonic within an intake and the log reads in
the order things happened.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.domain.record import (
    CanonicalRecord,
    DocumentKind,
    DocumentRef,
    DocumentStatus,
    Fact,
    IngestProvenance,
    IntakeStatus,
    PatientRef,
    PatientRefType,
    RedFlagEvent,
    live,
)
from app.models.clinical import (
    ClinicalFactRecord,
    DocumentRecordRow,
    IntakeRecord,
    RedFlagEventRecord,
)


def _fact_to_row(fact: Fact, *, hospital_id: str, intake_id: str, seq: int) -> ClinicalFactRecord:
    return ClinicalFactRecord(
        id=fact.fact_id,
        hospital_id=hospital_id,
        seq=seq,
        intake_id=intake_id,
        field_id=fact.field_id,
        section=fact.section.value,
        status=fact.status.value,
        certainty=fact.certainty.value,
        value=fact.value.model_dump(mode="json") if fact.value is not None else None,
        original_text=fact.original_text,
        language=fact.language,
        channel=fact.channel.value,
        source_ref=fact.source.model_dump(mode="json"),
        confidence=fact.confidence,
        reported_by=fact.reported_by.value,
        physician_verified=fact.physician_verified,
        physician_action=(
            fact.physician_action.value if fact.physician_action is not None else None
        ),
        repaired=fact.repaired,
        needs_verification=fact.needs_verification,
        recorded_at=fact.recorded_at,
        supersedes=fact.supersedes,
        note=fact.note,
    )


def _fact_from_row(row: ClinicalFactRecord) -> Fact:
    return Fact.model_validate(
        {
            "fact_id": row.id,
            "field_id": row.field_id,
            "status": row.status,
            "value": row.value,
            "original_text": row.original_text,
            "language": row.language,
            "source": row.source_ref,
            "confidence": row.confidence,
            "reported_by": row.reported_by,
            "certainty": row.certainty,
            "section": row.section,
            "channel": row.channel,
            "physician_verified": row.physician_verified,
            "physician_action": row.physician_action,
            "repaired": row.repaired,
            "needs_verification": row.needs_verification,
            "recorded_at": row.recorded_at,
            "supersedes": row.supersedes,
            "note": row.note,
        }
    )


def _document_from_row(row: DocumentRecordRow) -> DocumentRef:
    return DocumentRef(
        document_id=row.id,
        kind=DocumentKind(row.kind),
        status=DocumentStatus(row.status),
        page_count=row.page_count,
        confidence=row.overall_confidence,
        low_confidence=row.low_confidence,
        rejection_reason=row.rejection_reason,
        uploaded_at=row.uploaded_at,
        processed_at=row.processed_at,
    )


def _alert_from_row(row: RedFlagEventRecord) -> RedFlagEvent:
    return RedFlagEvent(
        rule_id=row.rule_id,
        fired_at_turn=row.fired_at_turn,
        criteria_met=tuple(row.criteria_met),
        severity=row.severity,
        label=row.label,
        acknowledged_by=row.acknowledged_by,
        acknowledged_at=row.acknowledged_at,
    )


class IntakeRepository:
    """Reads and writes intakes, facts, documents and red-flag events."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- writes -------------------------------------------------------------

    async def create(self, record: CanonicalRecord, *, received_at: datetime) -> IntakeRecord:
        """Persist a freshly ingested record.

        The whole record in one transaction: an intake row with no facts is a
        patient who answered questions and left no trace.
        """
        intake_id = str(record.intake_id)
        row = IntakeRecord(
            id=intake_id,
            hospital_id=record.hospital_id,
            patient_id=None,
            patient_ref_type=record.patient_ref.type.value,
            patient_ref_value=record.patient_ref.value,
            status=record.status.value,
            language=record.language,
            reported_by=record.reported_by.value,
            department_code=record.department_code,
            kiosk_id=record.provenance.kiosk_id,
            schema_version=record.provenance.schema_version,
            engine_version=record.provenance.engine_version,
            content_version=record.provenance.content_version,
            record_version=record.record_version,
            repaired=record.provenance.repaired,
            needs_manual_review=record.provenance.needs_manual_review,
            started_at=record.started_at,
            completed_at=record.completed_at,
            received_at=received_at,
        )
        self._session.add(row)

        for seq, fact in enumerate(record.facts):
            self._session.add(
                _fact_to_row(
                    fact, hospital_id=record.hospital_id, intake_id=intake_id, seq=seq
                )
            )

        for event in record.red_flags:
            self._session.add(
                RedFlagEventRecord(
                    id=f"rf_{intake_id}_{event.rule_id}",
                    hospital_id=record.hospital_id,
                    intake_id=intake_id,
                    rule_id=event.rule_id,
                    severity=event.severity,
                    label=event.label,
                    fired_at_turn=event.fired_at_turn,
                    criteria_met=list(event.criteria_met),
                    engine_version=record.provenance.engine_version,
                    received_at=received_at,
                )
            )

        await self._session.flush()
        return row

    async def append_facts(
        self, *, hospital_id: str, intake_id: str, facts: Sequence[Fact]
    ) -> None:
        """Add facts to an existing intake. Append-only."""
        if not facts:
            return
        next_seq = await self._next_seq(hospital_id=hospital_id, intake_id=intake_id)
        for offset, fact in enumerate(facts):
            self._session.add(
                _fact_to_row(
                    fact,
                    hospital_id=hospital_id,
                    intake_id=intake_id,
                    seq=next_seq + offset,
                )
            )
        await self._session.flush()

    async def _next_seq(self, *, hospital_id: str, intake_id: str) -> int:
        result = await self._session.execute(
            select(func.max(ClinicalFactRecord.seq)).where(
                ClinicalFactRecord.hospital_id == hospital_id,
                ClinicalFactRecord.intake_id == intake_id,
            )
        )
        current = result.scalar()
        return 0 if current is None else int(current) + 1

    async def mark_seen(
        self, *, hospital_id: str, intake_id: str, actor_id: str, at: datetime
    ) -> None:
        row = await self.get_row(hospital_id=hospital_id, intake_id=intake_id)
        row.seen_at = at
        row.seen_by = actor_id
        await self._session.flush()

    async def link_patient(
        self, *, hospital_id: str, intake_id: str, patient_id: str
    ) -> None:
        """Attach a guest intake to a registered patient after the fact."""
        row = await self.get_row(hospital_id=hospital_id, intake_id=intake_id)
        row.patient_id = patient_id
        await self._session.flush()

    # --- reads --------------------------------------------------------------

    async def get_row(self, *, hospital_id: str, intake_id: str) -> IntakeRecord:
        result = await self._session.execute(
            select(IntakeRecord).where(
                IntakeRecord.hospital_id == hospital_id, IntakeRecord.id == intake_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError(f"no intake {intake_id!r} at this hospital")
        return row

    async def exists(self, *, hospital_id: str, intake_id: str) -> bool:
        result = await self._session.execute(
            select(IntakeRecord.id).where(
                IntakeRecord.hospital_id == hospital_id, IntakeRecord.id == intake_id
            )
        )
        return result.scalar_one_or_none() is not None

    async def load(self, *, hospital_id: str, intake_id: str) -> CanonicalRecord:
        """Rebuild the canonical record from storage.

        Contradictions are recomputed by the caller rather than stored, so a
        change to the detector applies to records already in the database.
        """
        row = await self.get_row(hospital_id=hospital_id, intake_id=intake_id)

        facts_result = await self._session.execute(
            select(ClinicalFactRecord)
            .where(
                ClinicalFactRecord.hospital_id == hospital_id,
                ClinicalFactRecord.intake_id == intake_id,
            )
            .order_by(ClinicalFactRecord.seq)
        )
        documents_result = await self._session.execute(
            select(DocumentRecordRow)
            .where(
                DocumentRecordRow.hospital_id == hospital_id,
                DocumentRecordRow.intake_id == intake_id,
            )
            .order_by(DocumentRecordRow.uploaded_at)
        )
        alerts_result = await self._session.execute(
            select(RedFlagEventRecord)
            .where(
                RedFlagEventRecord.hospital_id == hospital_id,
                RedFlagEventRecord.intake_id == intake_id,
            )
            .order_by(RedFlagEventRecord.rule_id)
        )

        return CanonicalRecord(
            record_version=row.record_version,
            intake_id=row.id,
            hospital_id=row.hospital_id,
            patient_ref=PatientRef(
                type=PatientRefType(row.patient_ref_type), value=row.patient_ref_value
            ),
            language=row.language,
            status=IntakeStatus(row.status),
            reported_by=row.reported_by,
            department_code=row.department_code,
            facts=[_fact_from_row(f) for f in facts_result.scalars()],
            red_flags=[_alert_from_row(a) for a in alerts_result.scalars()],
            documents=[_document_from_row(d) for d in documents_result.scalars()],
            contradictions=[],
            provenance=IngestProvenance(
                schema_version=row.schema_version,
                engine_version=row.engine_version,
                content_version=row.content_version,
                kiosk_id=row.kiosk_id,
                repaired=row.repaired,
                needs_manual_review=row.needs_manual_review,
            ),
            started_at=row.started_at,
            completed_at=row.completed_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def for_department(
        self,
        *,
        hospital_id: str,
        department_code: str | None = None,
        since: datetime | None = None,
        limit: int = 200,
    ) -> Sequence[IntakeRecord]:
        statement = select(IntakeRecord).where(IntakeRecord.hospital_id == hospital_id)
        if department_code is not None:
            statement = statement.where(IntakeRecord.department_code == department_code)
        if since is not None:
            statement = statement.where(IntakeRecord.received_at >= since)
        statement = statement.order_by(IntakeRecord.received_at).limit(limit)
        result = await self._session.execute(statement)
        return list(result.scalars())

    async def history_for(
        self, *, hospital_id: str, ref_type: str, ref_value: str, limit: int = 20
    ) -> Sequence[IntakeRecord]:
        """Previous intakes for this patient **at this hospital only**.

        Cross-hospital retrieval requires ABDM consent and is out of scope; the
        `hospital_id` predicate here is what makes that a fact rather than a
        promise.
        """
        result = await self._session.execute(
            select(IntakeRecord)
            .where(
                IntakeRecord.hospital_id == hospital_id,
                IntakeRecord.patient_ref_type == ref_type,
                IntakeRecord.patient_ref_value == ref_value,
            )
            .order_by(IntakeRecord.received_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def unacknowledged_alert_counts(
        self, *, hospital_id: str, intake_ids: Sequence[str]
    ) -> dict[str, int]:
        if not intake_ids:
            return {}
        result = await self._session.execute(
            select(RedFlagEventRecord.intake_id, func.count())
            .where(
                RedFlagEventRecord.hospital_id == hospital_id,
                RedFlagEventRecord.intake_id.in_(list(intake_ids)),
                RedFlagEventRecord.acknowledged_by.is_(None),
            )
            .group_by(RedFlagEventRecord.intake_id)
        )
        return {intake_id: int(count) for intake_id, count in result.all()}

    async def alerts(
        self,
        *,
        hospital_id: str,
        acknowledged: bool | None = None,
        department_code: str | None = None,
        since: datetime | None = None,
        limit: int = 200,
    ) -> Sequence[tuple[RedFlagEventRecord, IntakeRecord]]:
        """Red-flag events with the intake each fired on — 3/3 §10.

        Joined rather than fetched in two passes because the alerts view needs
        the arrival time and the department, and a per-alert lookup for those is
        a query per row on the one screen that must not be slow.

        Unacknowledged first, then newest: the ordering is the triage view's
        whole argument, and doing it here means the API cannot forget it.
        """
        statement = (
            select(RedFlagEventRecord, IntakeRecord)
            .join(IntakeRecord, RedFlagEventRecord.intake_id == IntakeRecord.id)
            .where(RedFlagEventRecord.hospital_id == hospital_id)
        )
        if acknowledged is True:
            statement = statement.where(RedFlagEventRecord.acknowledged_by.is_not(None))
        elif acknowledged is False:
            statement = statement.where(RedFlagEventRecord.acknowledged_by.is_(None))
        if department_code is not None:
            statement = statement.where(IntakeRecord.department_code == department_code)
        if since is not None:
            statement = statement.where(RedFlagEventRecord.received_at >= since)
        statement = statement.order_by(
            # NULL acknowledgements sort first on both backends only if the
            # ordering is expressed as a predicate rather than as NULLS FIRST,
            # which SQLite does not accept.
            case((RedFlagEventRecord.acknowledged_by.is_(None), 0), else_=1),
            RedFlagEventRecord.received_at.desc(),
        ).limit(limit)
        result = await self._session.execute(statement)
        return [(alert, intake) for alert, intake in result.all()]

    async def facts_for(
        self, *, hospital_id: str, intake_ids: Sequence[str]
    ) -> dict[str, list[Fact]]:
        """Live facts for several intakes at once, keyed by intake.

        One query for the whole worklist rather than one per row. The worklist
        has to run the contradiction detector, the detector needs both channels
        of every fact, and a dashboard that polls every few seconds cannot
        afford a query per patient.
        """
        if not intake_ids:
            return {}
        result = await self._session.execute(
            select(ClinicalFactRecord)
            .where(
                ClinicalFactRecord.hospital_id == hospital_id,
                ClinicalFactRecord.intake_id.in_(list(intake_ids)),
            )
            .order_by(ClinicalFactRecord.intake_id, ClinicalFactRecord.seq)
        )
        grouped: dict[str, list[Fact]] = {}
        for row in result.scalars():
            grouped.setdefault(row.intake_id, []).append(_fact_from_row(row))
        return {intake_id: list(live(facts)) for intake_id, facts in grouped.items()}

    async def fact_counts(
        self, *, hospital_id: str, intake_ids: Sequence[str]
    ) -> dict[str, dict[str, Any]]:
        """Per-intake counters for the worklist.

        Counts, never content: this feeds a dashboard that may be visible from a
        waiting room.
        """
        if not intake_ids:
            return {}
        result = await self._session.execute(
            select(
                ClinicalFactRecord.intake_id,
                # `CASE` rather than a cast of the boolean: SQLite and Postgres
                # disagree about casting booleans to integers, and the
                # integration suite runs both.
                func.sum(case((ClinicalFactRecord.status == "unresolved", 1), else_=0)),
                func.sum(
                    case((ClinicalFactRecord.needs_verification.is_(True), 1), else_=0)
                ),
            )
            .where(
                ClinicalFactRecord.hospital_id == hospital_id,
                ClinicalFactRecord.intake_id.in_(list(intake_ids)),
            )
            .group_by(ClinicalFactRecord.intake_id)
        )
        return {
            intake_id: {
                "unresolved": int(unresolved or 0),
                "needs_verification": int(needs_verification or 0),
            }
            for intake_id, unresolved, needs_verification in result.all()
        }
