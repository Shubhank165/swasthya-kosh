"""FHIR R4 bundle.

A real, valid R4 document bundle — Patient, Encounter, Condition, Observation,
MedicationStatement, DocumentReference — generated from the canonical record.

This is worth more than a live ABDM call, and it works with no credentials. An
ABDM sandbox link proves an integration; a valid FHIR bundle proves the data
model, and the data model is the thing that has to be right before any
integration is worth building.

Two rules that shape everything below:

**Never invent a code.** A concept with no mapping in the terminology tables gets
`text` and no `coding`. A guessed ICD-11 code on a discharge summary is a wrong
diagnosis in someone's permanent record.

**Never assert what was not established.** The five-valued field status maps onto
FHIR's own vocabulary rather than being flattened: an unresolved field becomes an
Observation with `dataAbsentReason` of `unknown`, a refused one `asked-declined`,
an unasked one `not-asked`. FHIR has these codes precisely because the
distinction matters, and a bundle that collapsed them would be lying in a
standard format.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from app.domain.clinical.enums import Certainty, Section
from app.domain.record import (
    Boolean,
    CanonicalRecord,
    Coded,
    DateValue,
    DocumentRef,
    Fact,
    FieldStatus,
    PatientRefType,
    Quantity,
    Scale,
)

FHIR_VERSION = "4.0.1"

#: The base every `fullUrl` in the bundle is built from.
#:
#: Not `urn:uuid:` — that scheme requires an actual lowercase UUID, and these
#: ids are derived from fact ids so that a bundle can be diffed against an
#: earlier one. The published validator rejects `urn:uuid:obs-fact-...`, which
#: is the right call: a receiver reading it as a UUID would be reading a
#: malformed one.
FHIR_BASE_URL = "https://medikiosk.in/fhir"

#: The R4 `id` datatype: `[A-Za-z0-9\-\.]{1,64}`. Underscores are not in it,
#: and every fact id in this system contains one.
_ILLEGAL_IN_ID = re.compile(r"[^A-Za-z0-9.-]")


def resource_id(prefix: str, raw: str) -> str:
    """An R4-legal resource id derived from an internal one.

    Derived rather than generated, so the same record always produces the same
    bundle and a diff between two exports means something. Illegal characters
    are replaced rather than dropped — dropping them would map `a_b` and `ab`
    onto the same id — and anything over the 64-character limit keeps a prefix
    plus a hash of the whole original, so the truncation cannot collide either.
    """
    cleaned = _ILLEGAL_IN_ID.sub("-", raw).strip("-")
    candidate = f"{prefix}-{cleaned}"
    if len(candidate) <= 64:
        return candidate
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    keep = 64 - len(prefix) - len(digest) - 2
    return f"{prefix}-{cleaned[:keep]}-{digest}"

#: `dataAbsentReason` per unsettled status. Standard R4 codes; none of them is
#: `false`, and that is the point.
ABSENT_REASONS: Mapping[FieldStatus, tuple[str, str]] = {
    FieldStatus.UNRESOLVED: ("unknown", "Unknown"),
    FieldStatus.NOT_ASKED: ("not-asked", "Not Asked"),
    FieldStatus.REFUSED: ("asked-declined", "Asked But Declined"),
    FieldStatus.NOT_APPLICABLE: ("not-applicable", "Not Applicable"),
}

ABSENT_REASON_SYSTEM = "http://terminology.hl7.org/CodeSystem/data-absent-reason"

#: Sections whose facts become `Condition` resources rather than `Observation`.
CONDITION_SECTIONS: frozenset[Section] = frozenset(
    {Section.PAST_MEDICAL, Section.PAST_SURGICAL, Section.ALLERGIES}
)

#: System URIs. NAMASTE has no published canonical URI yet, so this is a
#: MediKiosk-scoped one, clearly marked as such rather than squatting on a
#: plausible-looking government domain.
SYSTEM_URIS: Mapping[str, str] = {
    "ICD11-MMS": "http://id.who.int/icd/release/11/mms",
    "ICD11-TM2": "http://id.who.int/icd/release/11/mms/tm2",
    "NAMASTE": "https://medikiosk.in/fhir/CodeSystem/namaste-local",
    "MEDIKIOSK": "https://medikiosk.in/fhir/CodeSystem/field",
}


def system_uri(system: str) -> str:
    return SYSTEM_URIS.get(system, f"https://medikiosk.in/fhir/CodeSystem/{system.lower()}")


class DeterministicFHIRMapper:
    """Canonical record -> FHIR R4 Bundle.

    Deterministic: same record, same bundle, byte for byte. Resource ids are
    derived from fact ids rather than generated, so a bundle can be diffed
    against an earlier one and the difference means something.
    """

    def __init__(
        self,
        *,
        codes: Mapping[str, Mapping[str, str]] | None = None,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        #: field_id -> {system: code}. Absent where no mapping exists.
        self._codes = codes or {}
        self._labels = labels or {}

    # --- helpers ------------------------------------------------------------

    def _label(self, field_id: str) -> str:
        return self._labels.get(field_id) or field_id.replace("_", " ")

    def _concept(self, field_id: str) -> dict[str, Any]:
        """A `CodeableConcept` for a field.

        `text` always. `coding` only when a mapping exists — a `CodeableConcept`
        with text and no coding is valid FHIR and is the honest representation
        of "we know what this is called, we have no code for it".
        """
        concept: dict[str, Any] = {"text": self._label(field_id)}
        codings = [
            {"system": system_uri(system), "code": code, "display": self._label(field_id)}
            for system, code in sorted(self._codes.get(field_id, {}).items())
        ]
        if codings:
            concept["coding"] = codings
        return concept

    def _patient_ref(self, record: CanonicalRecord) -> dict[str, str]:
        return {"reference": f"Patient/{resource_id('patient', str(record.intake_id))}"}

    def _encounter_ref(self, record: CanonicalRecord) -> dict[str, str]:
        return {"reference": f"Encounter/{resource_id('encounter', str(record.intake_id))}"}

    # --- resources ----------------------------------------------------------

    def _patient(self, record: CanonicalRecord) -> dict[str, Any]:
        """A Patient resource carrying identifiers and nothing else.

        No name, no address, no phone. This service is not a demographics store,
        and a bundle that carried them would make it one.
        """
        identifiers: list[dict[str, Any]] = []
        ref = record.patient_ref
        if ref.type is PatientRefType.ABHA and ref.value:
            identifiers.append(
                {"system": "https://healthid.abdm.gov.in/", "value": ref.value}
            )
        elif ref.type is PatientRefType.HOSPITAL_ID and ref.value:
            identifiers.append(
                {
                    "system": f"https://medikiosk.in/hospital/{record.hospital_id}/mrn",
                    "value": ref.value,
                }
            )
        # `aadhaar_last4` is deliberately never emitted. Four digits identify
        # nobody and putting them in an exchangeable document invites someone to
        # treat them as an identifier.
        return {
            "resourceType": "Patient",
            "id": resource_id("patient", str(record.intake_id)),
            "identifier": identifiers,
            "communication": [
                {
                    "language": {
                        "coding": [
                            {"system": "urn:ietf:bcp:47", "code": record.language}
                        ]
                    },
                    "preferred": True,
                }
            ],
        }

    def _encounter(self, record: CanonicalRecord) -> dict[str, Any]:
        period: dict[str, Any] = {}
        if record.started_at is not None:
            period["start"] = record.started_at.isoformat()
        if record.completed_at is not None:
            period["end"] = record.completed_at.isoformat()
        encounter: dict[str, Any] = {
            "resourceType": "Encounter",
            "id": resource_id("encounter", str(record.intake_id)),
            # `in-progress` for a partial intake, because the history-taking
            # genuinely did not finish and `finished` would say it did.
            "status": "finished" if record.status.value == "complete" else "in-progress",
            "class": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": "AMB",
                "display": "ambulatory",
            },
            "subject": self._patient_ref(record),
            "serviceProvider": {"display": record.hospital_id},
        }
        if period:
            encounter["period"] = period
        if record.department_code:
            encounter["serviceType"] = {"text": record.department_code}
        return encounter

    def _value(self, fact: Fact) -> dict[str, Any]:
        """The `value[x]` element for a fact, typed as FHIR types it."""
        value = fact.value
        if isinstance(value, Boolean):
            return {"valueBoolean": value.value}
        if isinstance(value, Quantity):
            return {
                "valueQuantity": {
                    "value": value.magnitude,
                    "unit": value.unit,
                    "system": "http://unitsofmeasure.org",
                }
            }
        if isinstance(value, Scale):
            return {
                "valueQuantity": {
                    "value": value.value,
                    "unit": f"score (0-{int(value.maximum)})",
                }
            }
        if isinstance(value, Coded):
            coding = {
                "system": system_uri(value.system) if value.system else system_uri("MEDIKIOSK"),
                "code": value.code,
            }
            if value.display:
                coding["display"] = value.display
            return {"valueCodeableConcept": {"coding": [coding], "text": value.render()}}
        if isinstance(value, DateValue):
            return {"valueDateTime": value.value.isoformat()}
        rendered = fact.rendered_value()
        return {"valueString": rendered} if rendered is not None else {}

    def _provenance_extensions(self, fact: Fact) -> list[dict[str, Any]]:
        """Certainty and provenance, as extensions.

        R4 has no field for "the patient hedged", and dropping that would let
        `"maybe two weeks"` leave this system as `2 weeks` — which is the exact
        thing the record model exists to prevent. So it travels as an extension:
        a consumer that ignores it loses nothing it had, and one that reads it
        gets the truth.
        """
        extensions: list[dict[str, Any]] = [
            {
                "url": "https://medikiosk.in/fhir/StructureDefinition/certainty",
                "valueCode": fact.certainty.value,
            },
            {
                "url": "https://medikiosk.in/fhir/StructureDefinition/field-status",
                "valueCode": fact.status.value,
            },
            {
                "url": "https://medikiosk.in/fhir/StructureDefinition/channel",
                "valueCode": fact.channel.value,
            },
        ]
        if fact.original_text:
            extensions.append(
                {
                    "url": "https://medikiosk.in/fhir/StructureDefinition/original-text",
                    "valueString": fact.original_text,
                }
            )
        if fact.repaired:
            extensions.append(
                {
                    "url": "https://medikiosk.in/fhir/StructureDefinition/repaired",
                    "valueBoolean": True,
                }
            )
        if fact.needs_verification:
            extensions.append(
                {
                    "url": "https://medikiosk.in/fhir/StructureDefinition/needs-verification",
                    "valueBoolean": True,
                }
            )
        return extensions

    def _observation(self, fact: Fact, record: CanonicalRecord) -> dict[str, Any]:
        observation: dict[str, Any] = {
            "resourceType": "Observation",
            "id": resource_id("obs", fact.fact_id),
            # `preliminary` unless a physician signed it off. Nothing this
            # system produces on its own is `final`.
            "status": "final" if fact.physician_verified else "preliminary",
            "category": [
                {
                    "coding": [
                        {
                            "system": (
                                "http://terminology.hl7.org/CodeSystem/observation-category"
                            ),
                            "code": "survey",
                            "display": "Survey",
                        }
                    ],
                    "text": fact.section.value,
                }
            ],
            "code": self._concept(fact.field_id),
            "subject": self._patient_ref(record),
            "encounter": self._encounter_ref(record),
            "effectiveDateTime": fact.recorded_at.isoformat(),
            "extension": self._provenance_extensions(fact),
        }
        if fact.status is FieldStatus.ANSWERED and fact.value is not None:
            observation.update(self._value(fact))
        else:
            code, display = ABSENT_REASONS.get(fact.status, ("unknown", "Unknown"))
            observation["dataAbsentReason"] = {
                "coding": [
                    {"system": ABSENT_REASON_SYSTEM, "code": code, "display": display}
                ]
            }
        return observation

    def _condition(self, fact: Fact, record: CanonicalRecord) -> dict[str, Any]:
        """A Condition, with its verification status told honestly.

        `unconfirmed` unless a physician verified it, and `refuted` only for an
        explicit answered denial. A field nobody asked about is neither — it is
        an Observation with `not-asked`, handled above.
        """
        if fact.denies():
            clinical, verification = "resolved", "refuted"
        elif fact.physician_verified:
            clinical, verification = "active", "confirmed"
        elif fact.certainty in {Certainty.APPROXIMATE, Certainty.UNCERTAIN}:
            clinical, verification = "active", "provisional"
        else:
            clinical, verification = "active", "unconfirmed"

        condition: dict[str, Any] = {
            "resourceType": "Condition",
            "id": resource_id("cond", fact.fact_id),
            "clinicalStatus": {
                "coding": [
                    {
                        "system": (
                            "http://terminology.hl7.org/CodeSystem/condition-clinical"
                        ),
                        "code": clinical,
                    }
                ]
            },
            "verificationStatus": {
                "coding": [
                    {
                        "system": (
                            "http://terminology.hl7.org/CodeSystem/condition-ver-status"
                        ),
                        "code": verification,
                    }
                ]
            },
            "code": self._concept(fact.field_id),
            "subject": self._patient_ref(record),
            "encounter": self._encounter_ref(record),
            "recordedDate": fact.recorded_at.isoformat(),
            "extension": self._provenance_extensions(fact),
        }
        return condition

    def _medication_statement(self, fact: Fact, record: CanonicalRecord) -> dict[str, Any]:
        return {
            "resourceType": "MedicationStatement",
            "id": resource_id("med", fact.fact_id),
            # `unknown` rather than `active`: the patient told us they take it,
            # which is not the same as our knowing they currently do.
            "status": "active" if fact.physician_verified else "unknown",
            "medicationCodeableConcept": {
                "text": fact.rendered_value() or self._label(fact.field_id)
            },
            "subject": self._patient_ref(record),
            "context": self._encounter_ref(record),
            "dateAsserted": fact.recorded_at.isoformat(),
            "informationSource": {"display": fact.reported_by.value},
            "extension": self._provenance_extensions(fact),
        }

    def _document_reference(
        self, document: DocumentRef, record: CanonicalRecord
    ) -> dict[str, Any]:
        return {
            "resourceType": "DocumentReference",
            "id": resource_id("docref", document.document_id),
            "status": "current",
            "docStatus": "final" if document.is_processed else "preliminary",
            "type": {"text": document.kind.value},
            "subject": self._patient_ref(record),
            "date": (
                document.uploaded_at.isoformat()
                if document.uploaded_at
                else record.created_at.isoformat()
            ),
            "content": [
                {
                    "attachment": {
                        "contentType": "image/jpeg",
                        "title": document.document_id,
                    }
                }
            ],
            "context": {"encounter": [self._encounter_ref(record)]},
        }

    # --- bundle -------------------------------------------------------------

    def to_bundle(self, record: CanonicalRecord) -> dict[str, Any]:
        """The complete R4 document bundle."""
        entries: list[dict[str, Any]] = [
            _entry(self._patient(record)),
            _entry(self._encounter(record)),
        ]

        for fact in sorted(record.live_facts(), key=lambda f: (f.field_id, f.fact_id)):
            if fact.section is Section.MEDICATIONS and fact.is_established:
                entries.append(_entry(self._medication_statement(fact, record)))
            elif fact.section in CONDITION_SECTIONS and fact.status is FieldStatus.ANSWERED:
                entries.append(_entry(self._condition(fact, record)))
            else:
                entries.append(_entry(self._observation(fact, record)))

        entries.extend(
            _entry(self._document_reference(document, record))
            for document in sorted(record.documents, key=lambda d: d.document_id)
        )

        return {
            "resourceType": "Bundle",
            "id": resource_id("intake", str(record.intake_id)),
            "meta": {"lastUpdated": _iso(record.updated_at)},
            "type": "collection",
            "timestamp": _iso(record.created_at),
            "entry": entries,
        }


def _entry(resource: dict[str, Any]) -> dict[str, Any]:
    """One bundle entry, with a `fullUrl` the relative references resolve against.

    An absolute URL under our own base, so `Patient/patient-…` inside a resource
    resolves to the entry carrying that tail — which is how a receiver links the
    bundle up without dereferencing anything.
    """
    return {
        "fullUrl": f"{FHIR_BASE_URL}/{resource['resourceType']}/{resource['id']}",
        "resource": resource,
    }


def _iso(value: datetime) -> str:
    return value.isoformat()


# --- terminology resources ---------------------------------------------------


def code_system_resource(
    system: str, concepts: Sequence[Mapping[str, Any]], *, version: str = "seed"
) -> dict[str, Any]:
    """A FHIR `CodeSystem` for one of the seeded vocabularies."""
    return {
        "resourceType": "CodeSystem",
        "id": system.lower().replace("-", ""),
        "url": system_uri(system),
        "version": version,
        "status": "draft",
        "content": "fragment",
        "concept": [
            {
                "code": str(concept["code"]),
                "display": str(concept["display"]),
                **(
                    {"definition": str(concept["definition"])}
                    if concept.get("definition")
                    else {}
                ),
            }
            for concept in concepts
        ],
    }


def concept_map_resource(
    mappings: Sequence[Mapping[str, Any]], *, name: str = "medikiosk-conceptmap"
) -> dict[str, Any]:
    """A FHIR `ConceptMap` from the seeded mapping table.

    Rows exist only where a mapping was authored. A code with no target simply
    is not here — the resource never asserts an equivalence nobody established.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in mappings:
        key = (str(row["source_system"]), str(row["target_system"]))
        groups.setdefault(key, []).append(
            {
                "code": str(row["source_code"]),
                "target": [
                    {
                        "code": str(row["target_code"]),
                        "equivalence": str(row.get("equivalence", "relatedto")),
                        **({"comment": str(row["note"])} if row.get("note") else {}),
                    }
                ],
            }
        )
    return {
        "resourceType": "ConceptMap",
        "id": name,
        "url": f"https://medikiosk.in/fhir/ConceptMap/{name}",
        "status": "draft",
        "group": [
            {
                "source": system_uri(source),
                "target": system_uri(target),
                "element": elements,
            }
            for (source, target), elements in sorted(groups.items())
        ],
    }


def value_set_resource(
    identifier: str, system: str, concepts: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """A FHIR `ValueSet` enumerating one system's seeded codes.

    Expanded rather than intensional, because the seed is a fragment: an
    intensional ValueSet would claim to include codes we do not hold and cannot
    resolve.
    """
    return {
        "resourceType": "ValueSet",
        "id": identifier,
        "url": f"https://medikiosk.in/fhir/ValueSet/{identifier}",
        "status": "draft",
        "compose": {
            "include": [
                {
                    "system": system_uri(system),
                    "concept": [
                        {"code": str(c["code"]), "display": str(c["display"])}
                        for c in concepts
                    ],
                }
            ]
        },
    }
