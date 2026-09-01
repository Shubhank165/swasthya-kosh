"""Consent endpoints.

The artefact is the deliverable here, not the boolean. DPDP Act 2023 requires we
can produce what was shown, in which language, when, and who granted it — so the
response carries the notice hash and the exact purpose codes, and there is no
endpoint that edits an artefact once written.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import (
    ConsentRepoDep,
    IdempotencyDep,
    IntakeServiceDep,
    PrincipalDep,
    idempotent,
)
from app.models.clinical import ConsentArtefact
from app.schemas.intake import ConsentOut, ConsentRequest

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
        granted_at=row.granted_at.isoformat(),
        withdrawn_at=row.withdrawn_at.isoformat() if row.withdrawn_at else None,
    )


@router.post("", response_model=ConsentOut, status_code=status.HTTP_201_CREATED)
async def record_consent(
    body: ConsentRequest,
    service: IntakeServiceDep,
    consent: ConsentRepoDep,
    guard: IdempotencyDep,
    _: PrincipalDep,
) -> ConsentOut:
    """Record what the patient agreed to.

    Refusing the base intake purpose is a valid outcome: the patient sees the
    doctor without a kiosk history, and their place in the queue is untouched.
    """

    async def produce() -> ConsentOut:
        artefact_id = await service.record_consent(
            body.intake_id,
            language=body.language,
            granted_purposes=body.granted_purposes,
            refused_purposes=body.refused_purposes,
            granting_party=body.granting_party.value,
            granting_party_name=body.granting_party_name,
            audio_asset_id=body.audio_asset_id,
        )
        return _out(await consent.require(artefact_id))

    return await idempotent(guard, ConsentOut, produce)


@router.get("/{consent_id}", response_model=ConsentOut)
async def get_consent(
    consent_id: str, consent: ConsentRepoDep, _: PrincipalDep
) -> ConsentOut:
    return _out(await consent.require(consent_id))


@router.get("/intake/{intake_id}/audio-retention", response_model=dict[str, bool])
async def audio_retention(
    intake_id: str, service: IntakeServiceDep, _: PrincipalDep
) -> dict[str, bool]:
    """Whether raw audio may be kept for this intake.

    Two independent gates: the facility setting and the patient's own grant of
    the `raw_audio_retention` purpose. Both must say yes.
    """
    return {"permitted": await service.audio_retention_permitted(intake_id)}
