"""Patient and hospital persistence.

`hospitals` is the tenant list and is queried unscoped — it is the one table
whose rows are not owned by a hospital, because they *are* the hospitals.
Everything else here filters.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.tenancy import unscoped
from app.models.clinical import HospitalRecord, PatientIdentifierLink, PatientRecord


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


class PatientLinkRepository:
    """Which identifiers point at which patient — `patient_identifier_links`.

    The table exists because history is keyed on the reference an intake was
    *filed under*, not on `patients.id`. `aliases_for` is what turns one
    reference into every reference that has ever resolved to the same person,
    and it is the whole of the "link my ABHA and see my phone visits" feature.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, *, hospital_id: str, ref_type: str, ref_value: str
    ) -> PatientIdentifierLink | None:
        result = await self._session.execute(
            select(PatientIdentifierLink).where(
                PatientIdentifierLink.hospital_id == hospital_id,
                PatientIdentifierLink.ref_type == ref_type,
                PatientIdentifierLink.ref_value == ref_value,
            )
        )
        return result.scalar_one_or_none()

    async def for_patient(
        self, *, hospital_id: str, patient_id: str
    ) -> Sequence[PatientIdentifierLink]:
        result = await self._session.execute(
            select(PatientIdentifierLink)
            .where(
                PatientIdentifierLink.hospital_id == hospital_id,
                PatientIdentifierLink.patient_id == patient_id,
            )
            # Deterministic, so an expanded alias set is stable between calls
            # and a history query built from it is reproducible.
            .order_by(PatientIdentifierLink.ref_type, PatientIdentifierLink.ref_value)
        )
        return list(result.scalars())

    async def aliases_for(
        self, *, hospital_id: str, ref_type: str, ref_value: str
    ) -> tuple[tuple[str, str], ...]:
        """Every reference that resolves to the same patient as this one.

        Always contains the reference passed in, even when nothing is linked —
        so a caller can use the result unconditionally and an unlinked patient
        behaves exactly as they did before this table existed.
        """
        me = (ref_type, ref_value)
        row = await self.get(
            hospital_id=hospital_id, ref_type=ref_type, ref_value=ref_value
        )
        if row is None or row.patient_id is None:
            # Known but not yet attached to a patient row, or not known at all.
            # Either way there is nobody to expand to.
            return (me,)
        siblings = await self.for_patient(
            hospital_id=hospital_id, patient_id=row.patient_id
        )
        refs = {(link.ref_type, link.ref_value) for link in siblings}
        refs.add(me)
        return tuple(sorted(refs))

    async def link(
        self,
        *,
        link_id: str,
        hospital_id: str,
        patient_id: str | None,
        ref_type: str,
        ref_value: str,
        source: str,
        linked_at: datetime,
    ) -> PatientIdentifierLink:
        """Attach a reference to a patient. Idempotent, but never silent.

        Re-linking the same pair is a no-op. Pointing an identifier that already
        resolves to one patient at a *different* one raises: that is either two
        people sharing a phone number or a mis-keyed ABHA address, and both are
        things a human has to look at. Merging them quietly would join two
        people's histories, which is the worst outcome this table can produce.
        """
        existing = await self.get(
            hospital_id=hospital_id, ref_type=ref_type, ref_value=ref_value
        )
        if existing is not None:
            if (
                existing.patient_id is not None
                and patient_id is not None
                and existing.patient_id != patient_id
            ):
                raise ConflictError(
                    f"{ref_type} reference is already linked to a different patient",
                    details={"ref_type": ref_type, "hospital_id": hospital_id},
                )
            if existing.patient_id is None and patient_id is not None:
                # Filling in a patient for an identifier seen before one
                # existed is the same assertion, not a competing one.
                existing.patient_id = patient_id
                await self._session.flush()
            return existing

        row = PatientIdentifierLink(
            id=link_id,
            hospital_id=hospital_id,
            patient_id=patient_id,
            ref_type=ref_type,
            ref_value=ref_value,
            source=source,
            linked_at=linked_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row
