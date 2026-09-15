"""The AYUSH/Prakriti self-report, read and written as whole revisions.

**Append-only, like every other record in this system.** There is no update
path here: a patient who answers the module again inserts a new row whose
`supersedes` points at the one it replaces, per decision 4. The current profile
is therefore the row nothing supersedes — not "the latest by timestamp", which
would pick the wrong row the first time two submissions raced or a clock
skewed.

Every query filters on `hospital_id`. The tenancy guard in `app/db/tenancy.py`
fails closed on one that does not, and decision 20 says an unscoped query raises
rather than being auto-scoped.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ayush_profile import AyushAnswer, AyushProfileSnapshot
from app.models.clinical import AyushProfileRecord


def snapshot_of(row: AyushProfileRecord | None) -> AyushProfileSnapshot | None:
    """A stored row as the frozen value the report builder is handed.

    Returns `None` for no row at all, which the builder reads as "this patient
    has not filled the module" — a different thing from an empty profile, and
    the report says so differently.
    """
    if row is None:
        return None
    answers = tuple(
        AyushAnswer(
            field_id=entry["field_id"],
            status=entry["status"],
            certainty=entry["certainty"],
            value=entry.get("value"),
            original_text=entry.get("original_text"),
        )
        for entry in row.answers
        if isinstance(entry, dict) and entry.get("field_id")
    )
    return AyushProfileSnapshot(
        answers=answers,
        language=row.language,
        content_version=row.content_version,
        submitted_at=row.submitted_at,
    )


class AyushProfileRepository:
    """Reads and writes `ayush_profiles`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def current(
        self, *, hospital_id: str, patient_ref_type: str, patient_ref_value: str
    ) -> AyushProfileRecord | None:
        """The live revision for one patient at one hospital.

        "The row nothing supersedes" rather than "the newest row": with an
        append-only table those are the same until they are not, and the case
        where they differ is the one that matters.
        """
        superseded = select(AyushProfileRecord.supersedes).where(
            AyushProfileRecord.hospital_id == hospital_id,
            AyushProfileRecord.supersedes.is_not(None),
        )
        result = await self._session.execute(
            select(AyushProfileRecord)
            .where(
                AyushProfileRecord.hospital_id == hospital_id,
                AyushProfileRecord.patient_ref_type == patient_ref_type,
                AyushProfileRecord.patient_ref_value == patient_ref_value,
                AyushProfileRecord.id.not_in(superseded),
            )
            .order_by(AyushProfileRecord.submitted_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def current_for_refs(
        self, *, hospital_id: str, refs: tuple[tuple[str, str], ...]
    ) -> AyushProfileRecord | None:
        """The live revision under any of one patient's identifiers.

        **This is what makes filing under `phone` safe.** A profile is stored
        against whatever reference the patient's session carried, and they may
        later attend under an ABHA address or a hospital UHID. Looking it up by
        the visit's own reference alone would miss it — the profile would exist,
        belong to that patient, and be invisible on their report, which is the
        failure `PatientIdentifierLink` exists to prevent. The caller expands
        the reference through `aliases_for` and passes the whole set here.

        Newest wins if two identifiers somehow carry live revisions. That is
        already an anomaly — a patient should have one live profile per hospital
        — and the newest is the one they most recently intended.
        """
        if not refs:
            return None
        superseded = select(AyushProfileRecord.supersedes).where(
            AyushProfileRecord.hospital_id == hospital_id,
            AyushProfileRecord.supersedes.is_not(None),
        )
        matches = or_(
            *(
                and_(
                    AyushProfileRecord.patient_ref_type == ref_type,
                    AyushProfileRecord.patient_ref_value == ref_value,
                )
                for ref_type, ref_value in refs
            )
        )
        result = await self._session.execute(
            select(AyushProfileRecord)
            .where(
                AyushProfileRecord.hospital_id == hospital_id,
                matches,
                AyushProfileRecord.id.not_in(superseded),
            )
            .order_by(AyushProfileRecord.submitted_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def add_revision(
        self,
        *,
        profile_id: str,
        hospital_id: str,
        patient_ref_type: str,
        patient_ref_value: str,
        language: str,
        content_version: str | None,
        answers: list[dict[str, object]],
        submitted_at: datetime,
        supersedes: str | None,
    ) -> AyushProfileRecord:
        """Insert one revision. Never updates an existing row."""
        row = AyushProfileRecord(
            id=profile_id,
            hospital_id=hospital_id,
            patient_ref_type=patient_ref_type,
            patient_ref_value=patient_ref_value,
            language=language,
            content_version=content_version,
            answers=answers,
            submitted_at=submitted_at,
            supersedes=supersedes,
        )
        self._session.add(row)
        await self._session.flush()
        return row
