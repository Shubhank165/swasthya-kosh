"""Intake repository.

The fact log is append-only: `save` diffs the in-memory state against what is
already persisted and inserts only the new rows. There is no UPDATE on
`clinical_facts` anywhere in this codebase, and there must never be one.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.domain.clinical.enums import IntakeState
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.clinical.provenance import IntakeId
from app.models.clinical import ClinicalFactRecord, DocumentRecordRow, IntakeRecord
from app.repositories.mappers import (
    apply_intake_to_row,
    fact_to_row,
    intake_from_rows,
)


class IntakeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        intake_id: str,
        started_at: datetime,
        kiosk_id: str | None = None,
        department_code: str | None = None,
        patient_id: str | None = None,
        language: str | None = None,
    ) -> PatientIntakeState:
        row = IntakeRecord(
            id=intake_id,
            patient_id=patient_id,
            state=IntakeState.NOT_STARTED.value,
            revision=0,
            language=language,
            reporter_role="self",
            active_ros_groups=[],
            declined_concepts=[],
            kiosk_id=kiosk_id,
            department_code=department_code,
            started_at=started_at,
            last_activity_at=started_at,
        )
        self._session.add(row)
        await self._session.flush()
        return intake_from_rows(row, [], [])

    async def get(self, intake_id: str) -> PatientIntakeState | None:
        row = await self._session.get(IntakeRecord, intake_id)
        if row is None:
            return None
        facts = list(
            (
                await self._session.execute(
                    select(ClinicalFactRecord)
                    .where(ClinicalFactRecord.intake_id == intake_id)
                    .order_by(ClinicalFactRecord.seq)
                )
            )
            .scalars()
            .all()
        )
        documents = list(
            (
                await self._session.execute(
                    select(DocumentRecordRow)
                    .where(DocumentRecordRow.intake_id == intake_id)
                    .order_by(DocumentRecordRow.uploaded_at)
                )
            )
            .scalars()
            .all()
        )
        return intake_from_rows(row, facts, documents)

    async def require(self, intake_id: str) -> PatientIntakeState:
        state = await self.get(intake_id)
        if state is None:
            raise NotFoundError(f"intake {intake_id} not found", details={"intake_id": intake_id})
        return state

    async def row(self, intake_id: str) -> IntakeRecord:
        row = await self._session.get(IntakeRecord, intake_id)
        if row is None:
            raise NotFoundError(f"intake {intake_id} not found", details={"intake_id": intake_id})
        return row

    async def save(self, state: PatientIntakeState, *, now: datetime) -> None:
        """Persist session metadata and append any facts not already stored."""
        row = await self.row(str(state.intake_id))
        apply_intake_to_row(row, state)
        row.last_activity_at = now

        existing = set(
            (
                await self._session.execute(
                    select(ClinicalFactRecord.id).where(
                        ClinicalFactRecord.intake_id == str(state.intake_id)
                    )
                )
            )
            .scalars()
            .all()
        )
        max_seq = len(existing)
        for offset, fact in enumerate(f for f in state.facts if str(f.fact_id) not in existing):
            self._session.add(
                fact_to_row(fact, intake_id=str(state.intake_id), seq=max_seq + offset)
            )
        await self._session.flush()

    async def list_stale(
        self, *, before: datetime, states: tuple[IntakeState, ...]
    ) -> tuple[str, ...]:
        """Intakes with no activity since `before`, for the inactivity sweep."""
        result = await self._session.execute(
            select(IntakeRecord.id).where(
                IntakeRecord.last_activity_at < before,
                IntakeRecord.state.in_([s.value for s in states]),
            )
        )
        return tuple(result.scalars().all())

    async def purge_session_state(self, intake_id: str) -> None:
        """Clear kiosk-linkage on teardown.

        The clinical record stays — it belongs to the encounter. What is dropped
        is the association with the physical kiosk, so the next patient at that
        terminal cannot reach the previous patient's session.
        """
        row = await self.row(intake_id)
        row.kiosk_id = None
        await self._session.flush()

    async def find_by_kiosk(self, kiosk_id: str) -> tuple[IntakeId, ...]:
        result = await self._session.execute(
            select(IntakeRecord.id).where(IntakeRecord.kiosk_id == kiosk_id)
        )
        return tuple(IntakeId(v) for v in result.scalars().all())
