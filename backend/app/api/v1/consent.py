"""Consent — §9.

Consent is stored as a record you could produce in an audit: the exact text
shown, the language it was shown in, the audio actually played, the purposes
granted, when, and by whom. Not a boolean.

The DPDP Act 2023 requires we can produce this. A boolean would not survive a
single question from a regulator, and it would not survive one from a patient
either.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.auth import RequireKioskOrStaff, RequireStaff
from app.api.deps import ClockDep, ConsentRepoDep, IdsDep
from app.models.clinical import ConsentArtefact
from app.schemas.api import ConsentOut, ConsentRequest

router = APIRouter(prefix="/consent", tags=["consent"])


def _out(row: ConsentArtefact) -> ConsentOut:
    return ConsentOut(
        consent_id=row.id,
        intake_id=row.intake_id,
        consent_version=row.consent_version,
        language=row.language,
        notice_hash=row.notice_hash,
        granted_purposes=list(row.granted_purposes or []),
        refused_purposes=list(row.refused_purposes or []),
        granting_party=row.granting_party,
        granted_at=row.granted_at,
        withdrawn_at=row.withdrawn_at,
    )


@router.post(
    "",
    response_model=ConsentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a consent artefact",
)
async def record_consent(
    principal: RequireKioskOrStaff,
    repository: ConsentRepoDep,
    clock: ClockDep,
    ids: IdsDep,
    request: ConsentRequest,
) -> ConsentOut:
    """Store what the patient actually agreed to.

    Immutable. A withdrawal or a re-take writes a new artefact that supersedes
    this one; nothing edits a row here, because a row that can be edited proves
    nothing about what was shown at the time.
    """
    row = await repository.record(
        artefact_id=ids.new_id("consent"),
        hospital_id=principal.hospital_id,
        intake_id=request.intake_id,
        patient_id=request.patient_id,
        consent_version=request.consent_version,
        language=request.language,
        notice_text=request.notice_text,
        granted_purposes=request.granted_purposes,
        refused_purposes=request.refused_purposes,
        granting_party=request.granting_party,
        granting_party_name=request.granting_party_name,
        audio_asset_id=request.audio_asset_id,
        granted_at=clock.now(),
    )
    return _out(row)


@router.get(
    "/{consent_id}",
    response_model=ConsentOut,
    summary="Retrieve a consent artefact",
)
async def get_consent(
    consent_id: str,
    principal: RequireStaff,
    repository: ConsentRepoDep,
) -> ConsentOut:
    return _out(
        await repository.require(
            hospital_id=principal.hospital_id, artefact_id=consent_id
        )
    )
