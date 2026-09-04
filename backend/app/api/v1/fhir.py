"""FHIR R4 export — §10.

A real, valid R4 bundle, generated from the canonical record with no
credentials and no network. This is worth more than a live ABDM call: an ABDM
link proves an integration, a valid bundle proves the data model, and the data
model has to be right before the integration is worth building.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Response

from app.adapters.fhir.mapper import DeterministicFHIRMapper
from app.api.auth import RequireStaff
from app.api.deps import ContentDep, ReportServiceDep, TerminologyServiceDep

router = APIRouter(prefix="/fhir", tags=["fhir"])


@router.get(
    "/intakes/{intake_id}",
    summary="FHIR R4 bundle for one intake",
)
async def intake_bundle(
    intake_id: str,
    principal: RequireStaff,
    service: ReportServiceDep,
    content: ContentDep,
    terminology: TerminologyServiceDep,
) -> Response:
    """Patient, Encounter, Condition, Observation, MedicationStatement,
    DocumentReference.

    Codes appear only where a mapping exists. A field with no code gets `text`
    and no `coding` — a valid `CodeableConcept`, and the honest representation
    of "we know what this is, we have no code for it". A guessed code in an
    exchangeable document is a wrong diagnosis in someone's permanent record.
    """
    record = await service.load_record(
        hospital_id=principal.hospital_id, intake_id=intake_id
    )
    mapper = DeterministicFHIRMapper(
        codes={c.concept_id: dict(c.codes) for c in content.concepts},
        labels=content.field_labels(),
    )
    bundle: dict[str, Any] = mapper.to_bundle(record)
    return Response(
        content=json.dumps(bundle, ensure_ascii=False, indent=2),
        media_type="application/fhir+json",
    )
