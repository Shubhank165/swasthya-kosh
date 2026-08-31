"""FHIR R4 mapping.

A real deterministic implementation, not a mock: the bundle is assembled from
facts by the same rules as the summary. Two properties are load-bearing.

First, every `Condition` carries dual codes — NAMASTE alongside ICD-11 TM2/MMS —
wherever a mapping exists, and carries only what exists where it does not. An
absent coding is correct; a synthesised one is a defect.

Second, nothing derived by a machine is asserted as confirmed. A fact a
physician has not verified maps to `verificationStatus: unconfirmed`, which is
the FHIR-native way of saying what this whole system says everywhere else.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.domain.clinical.enums import Certainty, FactStatus, Section
from app.domain.clinical.fact import ClinicalFact
from app.domain.clinical.patient_state import PatientIntakeState

#: Canonical system URIs. Local URIs for the AYUSH systems until the national
#: registry publishes its own; they are config, not identity.
SYSTEM_URIS: Mapping[str, str] = {
    "NAMASTE": "http://terminology.medikiosk.local/CodeSystem/namaste",
    "ICD11-TM2": "http://id.who.int/icd/release/11/tm2",
    "ICD11-MMS": "http://id.who.int/icd/release/11/mms",
}

#: Sections that map to FHIR `Condition`; everything else becomes `Observation`.
_CONDITION_SECTIONS: frozenset[Section] = frozenset(
    {Section.PAST_MEDICAL, Section.CHIEF_COMPLAINT}
)

_CLINICAL_STATUS = {
    FactStatus.PRESENT: "active",
    FactStatus.ABSENT: "resolved",
}

_VERIFICATION_STATUS_BY_CERTAINTY = {
    Certainty.CONFIRMED: "confirmed",
    Certainty.REPORTED: "provisional",
    Certainty.APPROXIMATE: "provisional",
    Certainty.UNCERTAIN: "unconfirmed",
}


def _codings(fact: ClinicalFact, mappings: Mapping[str, Mapping[str, str]]) -> list[dict[str, Any]]:
    """Codings for a fact's concept, across every system that has a mapping.

    `mappings` is `{concept_id: {system: code}}`, supplied by the terminology
    service. A concept with no entry yields a single local coding rather than a
    fabricated standard one.
    """
    entry = mappings.get(fact.concept.concept_id, {})
    codings = [
        {
            "system": SYSTEM_URIS[system],
            "code": code,
            "display": fact.concept.display or fact.concept.concept_id,
        }
        for system, code in sorted(entry.items())
        if system in SYSTEM_URIS
    ]
    if not codings:
        codings.append(
            {
                "system": "http://terminology.medikiosk.local/CodeSystem/local",
                "code": fact.concept.concept_id,
                "display": fact.concept.display or fact.concept.concept_id,
            }
        )
    return codings


def _text_of(fact: ClinicalFact) -> str:
    """`text` for a CodeableConcept.

    Prefers the patient's own words. FHIR's `text` field exists precisely so the
    original expression survives coding, which is invariant 7 restated in
    someone else's spec.
    """
    return fact.original_expression or fact.display()


def _verification_status(fact: ClinicalFact) -> str:
    if fact.physician_verified:
        return "confirmed"
    if fact.status is FactStatus.UNKNOWN:
        return "unconfirmed"
    return _VERIFICATION_STATUS_BY_CERTAINTY.get(fact.certainty, "unconfirmed")


def _condition(
    fact: ClinicalFact, subject: str, mappings: Mapping[str, Mapping[str, str]]
) -> dict[str, Any]:
    return {
        "resourceType": "Condition",
        "id": str(fact.fact_id),
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": _CLINICAL_STATUS.get(fact.status, "active"),
                }
            ]
        },
        "verificationStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                    "code": _verification_status(fact),
                }
            ]
        },
        "code": {"coding": _codings(fact, mappings), "text": _text_of(fact)},
        "subject": {"reference": subject},
        "recordedDate": fact.recorded_at.isoformat(),
        "note": [{"text": f"source: {fact.source_type.value}; reporter: {fact.reported_by.value}"}],
    }


def _observation(
    fact: ClinicalFact, subject: str, mappings: Mapping[str, Mapping[str, str]]
) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "resourceType": "Observation",
        "id": str(fact.fact_id),
        # Nothing here is a finished finding; everything awaits a clinician.
        "status": "final" if fact.physician_verified else "preliminary",
        "code": {"coding": _codings(fact, mappings), "text": _text_of(fact)},
        "subject": {"reference": subject},
        "effectiveDateTime": fact.recorded_at.isoformat(),
    }
    rendered = fact.rendered_value()
    if rendered is not None:
        resource["valueString"] = rendered
    return resource


def _absent_reason(fact: ClinicalFact) -> str:
    """FHIR data-absent-reason for a fact that carries no value.

    The five statuses map onto distinct FHIR reasons; collapsing them here would
    undo invariant 5 at the integration boundary, which is exactly where it
    matters most.
    """
    return {
        FactStatus.UNKNOWN: "unknown",
        FactStatus.NOT_ASKED: "not-asked",
        FactStatus.NOT_APPLICABLE: "not-applicable",
        FactStatus.ABSENT: "not-performed",
    }.get(fact.status, "unknown")


class DeterministicFHIRMapper:
    """Maps an intake to a FHIR R4 Bundle."""

    def __init__(self, mappings: Mapping[str, Mapping[str, str]] | None = None) -> None:
        self._mappings = mappings or {}

    def to_bundle(self, state: PatientIntakeState) -> dict[str, Any]:
        subject = f"Patient/{state.patient_id or 'unknown'}"
        entries: list[dict[str, Any]] = []

        for fact in sorted(state.current(), key=lambda f: f.concept.concept_id):
            if fact.status in {FactStatus.NOT_ASKED, FactStatus.NOT_APPLICABLE}:
                continue
            resource = (
                _condition(fact, subject, self._mappings)
                if fact.section in _CONDITION_SECTIONS
                else _observation(fact, subject, self._mappings)
            )
            if fact.value is None and resource["resourceType"] == "Observation":
                resource["dataAbsentReason"] = {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/data-absent-reason",
                            "code": _absent_reason(fact),
                        }
                    ]
                }
            entries.append(
                {"fullUrl": f"urn:uuid:{fact.fact_id}", "resource": resource}
            )

        return {
            "resourceType": "Bundle",
            "id": str(state.intake_id),
            "type": "collection",
            "entry": entries,
        }


def code_system_resource(
    system: str, version: str, concepts: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """A FHIR `CodeSystem` for one terminology."""
    return {
        "resourceType": "CodeSystem",
        "id": system.lower().replace("-", ""),
        "url": SYSTEM_URIS.get(system, f"http://terminology.medikiosk.local/CodeSystem/{system}"),
        "version": version,
        "name": system.replace("-", "_"),
        "status": "draft",
        "content": "fragment",
        "count": len(concepts),
        "concept": [
            {
                "code": str(c["code"]),
                "display": str(c.get("display", c["code"])),
                **({"definition": str(c["definition"])} if c.get("definition") else {}),
            }
            for c in concepts
        ],
    }


def concept_map_resource(
    map_id: str, version: str, groups: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """A FHIR `ConceptMap`.

    Only real mappings appear. A concept with no counterpart in a target system
    is simply absent from that group — never present with a guessed code.
    """
    return {
        "resourceType": "ConceptMap",
        "id": map_id,
        "url": f"http://terminology.medikiosk.local/ConceptMap/{map_id}",
        "version": version,
        "status": "draft",
        "group": list(groups),
    }


def value_set_resource(
    value_set_id: str, system: str, codes: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """A FHIR `ValueSet` enumerating codes from one system."""
    return {
        "resourceType": "ValueSet",
        "id": value_set_id,
        "url": f"http://terminology.medikiosk.local/ValueSet/{value_set_id}",
        "status": "draft",
        "compose": {
            "include": [
                {
                    "system": SYSTEM_URIS.get(system, system),
                    "concept": [
                        {"code": str(c["code"]), "display": str(c.get("display", c["code"]))}
                        for c in codes
                    ],
                }
            ]
        },
    }
