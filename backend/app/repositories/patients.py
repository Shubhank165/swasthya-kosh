"""Patient and hospital persistence.

`hospitals` is the tenant list and is queried unscoped — it is the one table
whose rows are not owned by a hospital, because they *are* the hospitals.
Everything else here filters.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.tenancy import unscoped
from app.models.clinical import HospitalRecord, PatientRecord


class HospitalRepository:
    """The tenant list."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, hospital_id: str) -> HospitalRecord | None:
        with unscoped():
            result = await self._session.execute(
                select(HospitalRecord).where(HospitalRecord.id == hospital_id)
            )
            return result.scalar_one_or_none()

    async def require(self, hospital_id: str) -> HospitalRecord:
        row = await self.get(hospital_id)
        if row is None:
            raise NotFoundError(f"unknown hospital {hospital_id!r}")
        return row

    async def all(self) -> Sequence[HospitalRecord]:
        with unscoped():
            result = await self._session.execute(
                select(HospitalRecord).order_by(HospitalRecord.id)
            )
            return list(result.scalars())

    async def create(
        self,
        *,
        hospital_id: str,
        display_name: str,
        departments: list[str],
        location: str | None = None,
        timezone: str = "Asia/Kolkata",
        default_language: str = "en",
    ) -> HospitalRecord:
        with unscoped():
            row = HospitalRecord(
                id=hospital_id,
                display_name=display_name,
                location=location,
                timezone=timezone,
                departments=departments,
                default_language=default_language,
            )
            self._session.add(row)
            await self._session.flush()
            return row


class PatientRepository:
    """Minimal identity, scoped to one hospital."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, hospital_id: str, patient_id: str) -> PatientRecord | None:
        result = await self._session.execute(
            select(PatientRecord).where(
                PatientRecord.hospital_id == hospital_id, PatientRecord.id == patient_id
            )
        )
        return result.scalar_one_or_none()

    async def by_mrn(self, *, hospital_id: str, mrn: str) -> PatientRecord | None:
        result = await self._session.execute(
            select(PatientRecord).where(
                PatientRecord.hospital_id == hospital_id,
                PatientRecord.external_mrn == mrn,
            )
        )
        return result.scalar_one_or_none()

    async def by_abha(self, *, hospital_id: str, abha_address: str) -> PatientRecord | None:
        result = await self._session.execute(
            select(PatientRecord).where(
                PatientRecord.hospital_id == hospital_id,
                PatientRecord.abha_address == abha_address,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        patient_id: str,
        hospital_id: str,
        external_mrn: str | None = None,
        abha_address: str | None = None,
        display_name: str | None = None,
        birth_year: int | None = None,
        sex: str | None = None,
        preferred_language: str | None = None,
    ) -> PatientRecord:
        row = PatientRecord(
            id=patient_id,
            hospital_id=hospital_id,
            external_mrn=external_mrn,
            abha_address=abha_address,
            display_name=display_name,
            birth_year=birth_year,
            sex=sex,
            preferred_language=preferred_language,
        )
        self._session.add(row)
        await self._session.flush()
        return row
