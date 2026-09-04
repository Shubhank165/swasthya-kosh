"""Patient identity and history retrieval — §8.

Four kinds of patient reference, and **ABHA is never mandatory**: `abha`,
`hospital_id`, `aadhaar_last4` (a matching aid, never stored whole) and `guest`.

A guest intake is complete and valid on its own. Somebody who walks into an OPD
without a card, without a phone and without an ABHA address still gets a
structured history, and registration links it to a patient later. Requiring an
identifier before the interview would exclude precisely the patients this is
supposed to help.

History retrieval is **this hospital only**. Cross-hospital retrieval requires
ABDM consent and is out of scope; the `hospital_id` predicate in the repository
is what makes that a fact rather than an intention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.adapters.protocols import ABHAProvider
from app.core.clock import Clock
from app.core.errors import ValidationError
from app.core.ids import IdFactory
from app.core.logging import get_logger
from app.domain.clinical.enums import Section
from app.domain.record import FieldStatus, PatientRef, PatientRefType
from app.repositories.intakes import IntakeRepository
from app.repositories.patients import PatientRepository

logger = get_logger(__name__)

#: What the Jetson pre-loads. The doctor's confirmed conditions, medicines and
#: allergies — so the next intake can ask "our record shows diabetes, still
#: correct?" instead of starting from nothing.
CARRY_FORWARD_SECTIONS: frozenset[Section] = frozenset(
    {Section.PAST_MEDICAL, Section.MEDICATIONS, Section.ALLERGIES}
)


@dataclass(frozen=True, slots=True)
class ResolvedPatient:
    """The answer to `POST /patients/resolve`."""

    ref: PatientRef
    patient_id: str | None = None
    #: `"mock"` when the ABHA answer came from the mock provider. Surfaced
    #: through the API so the dashboard and the demo can say so out loud.
    source: str | None = None
    verified: bool = False
    notice: str | None = None
    known_here: bool = False

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "ref": {"type": self.ref.type.value, "value": self.ref.value},
            "patient_id": self.patient_id,
            "verified": self.verified,
            "known_here": self.known_here,
        }
        if self.source is not None:
            body["source"] = self.source
        if self.notice is not None:
            body["notice"] = self.notice
        return body


@dataclass(frozen=True, slots=True)
class CarriedFact:
    """One thing worth carrying into the next intake.

    Only physician-verified facts qualify. Carrying forward an unverified
    patient-reported condition would let a mishearing become permanent history
    by being repeated back at the patient as something "our record shows".
    """

    field_id: str
    label: str
    value: str | None
    section: str
    verified_at: str
    intake_id: str


@dataclass(frozen=True, slots=True)
class PatientHistory:
    """Previous intakes at this hospital, and what to pre-load."""

    ref: PatientRef
    hospital_id: str
    intakes: list[dict[str, Any]] = field(default_factory=list)
    carry_forward: list[CarriedFact] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": {"type": self.ref.type.value, "value": self.ref.value},
            "hospital_id": self.hospital_id,
            "intakes": self.intakes,
            "carry_forward": [
                {
                    "field_id": c.field_id,
                    "label": c.label,
                    "value": c.value,
                    "section": c.section,
                    "verified_at": c.verified_at,
                    "intake_id": c.intake_id,
                }
                for c in self.carry_forward
            ],
            "scope_note": (
                "Records held by this hospital only. Retrieval across hospitals "
                "requires an ABDM consent artefact and is not implemented."
            ),
        }


def parse_ref(raw: str) -> PatientRef:
    """`abha:name@sbx`, `hospital_id:UHID-123`, `guest`, or a bare ABHA address."""
    text = raw.strip()
    if not text:
        raise ValidationError("an empty patient reference is not a reference")
    if text == "guest":
        return PatientRef(type=PatientRefType.GUEST)
    if ":" not in text:
        # A bare value. An `@` makes it an ABHA address; anything else is the
        # hospital's own identifier, which is the common case at a counter.
        kind = PatientRefType.ABHA if "@" in text else PatientRefType.HOSPITAL_ID
        return PatientRef(type=kind, value=text)
    prefix, _, value = text.partition(":")
    try:
        ref_type = PatientRefType(prefix)
    except ValueError as exc:
        raise ValidationError(
            f"unknown patient reference type {prefix!r}",
            details={"supported": [t.value for t in PatientRefType]},
        ) from exc
    return PatientRef(type=ref_type, value=value or None)


class IdentityService:
    """Resolves patient references and retrieves prior records."""

    def __init__(
        self,
        *,
        patients: PatientRepository,
        intakes: IntakeRepository,
        abha: ABHAProvider,
        clock: Clock,
        ids: IdFactory,
        labels: dict[str, str] | None = None,
    ) -> None:
        self._patients = patients
        self._intakes = intakes
        self._abha = abha
        self._clock = clock
        self._ids = ids
        self._labels = labels or {}

    async def resolve(self, ref: PatientRef, *, hospital_id: str) -> ResolvedPatient:
        """Identify a patient, without ever requiring that identification succeed.

        A failed ABHA lookup does not fail the request. It comes back
        unverified, and the intake proceeds as a guest — the alternative is
        turning someone away because a government API was down.
        """
        if ref.type is PatientRefType.GUEST:
            return ResolvedPatient(ref=ref, verified=False)

        if ref.type is PatientRefType.HOSPITAL_ID:
            assert ref.value is not None
            row = await self._patients.by_mrn(hospital_id=hospital_id, mrn=ref.value)
            return ResolvedPatient(
                ref=ref,
                patient_id=row.id if row else None,
                verified=row is not None,
                known_here=row is not None,
                source="hospital_registry",
            )

        if ref.type is PatientRefType.AADHAAR_LAST4:
            # A matching aid, nothing more. Four digits identify nobody, and
            # this deliberately never verifies anything.
            return ResolvedPatient(
                ref=ref,
                verified=False,
                source="local",
                notice=(
                    "The last four digits of an Aadhaar number are a matching aid "
                    "only. No verification was performed and the whole number is "
                    "neither requested nor stored."
                ),
            )

        assert ref.value is not None
        result = await self._abha.verify(ref.value)
        row = await self._patients.by_abha(hospital_id=hospital_id, abha_address=ref.value)
        if result is None:
            return ResolvedPatient(
                ref=ref,
                patient_id=row.id if row else None,
                verified=False,
                known_here=row is not None,
                source=self._abha.name,
                notice="ABHA address could not be verified. Intake may proceed as guest.",
            )
        return ResolvedPatient(
            ref=ref,
            patient_id=row.id if row else None,
            verified=bool(result.get("verified")),
            known_here=row is not None,
            # `"mock"` travels all the way to the client. A mocked government
            # integration is never presented as a live one.
            source=str(result.get("source", self._abha.name)),
            notice=result.get("notice"),
        )

    async def history(
        self, ref: PatientRef, *, hospital_id: str, limit: int = 20
    ) -> PatientHistory:
        """Prior intakes, and what the Jetson should pre-load."""
        if ref.type is PatientRefType.GUEST or ref.value is None:
            # A guest has no history by construction. Returning an empty result
            # rather than an error keeps the kiosk's flow identical either way.
            return PatientHistory(ref=ref, hospital_id=hospital_id)

        rows = await self._intakes.history_for(
            hospital_id=hospital_id,
            ref_type=ref.type.value,
            ref_value=ref.value,
            limit=limit,
        )
        summaries = [
            {
                "intake_id": row.id,
                "status": row.status,
                "language": row.language,
                "department_code": row.department_code,
                "received_at": row.received_at.isoformat(),
                "seen_at": row.seen_at.isoformat() if row.seen_at else None,
            }
            for row in rows
        ]

        carried: dict[str, CarriedFact] = {}
        for row in rows:
            record = await self._intakes.load(hospital_id=hospital_id, intake_id=row.id)
            for fact in record.live_facts():
                if fact.section not in CARRY_FORWARD_SECTIONS:
                    continue
                if not fact.physician_verified:
                    continue
                if fact.status is not FieldStatus.ANSWERED:
                    continue
                # Rows are newest-first, so the first sighting of a field is the
                # most recent confirmation of it.
                carried.setdefault(
                    fact.field_id,
                    CarriedFact(
                        field_id=fact.field_id,
                        label=self._labels.get(fact.field_id)
                        or fact.field_id.replace("_", " "),
                        value=fact.rendered_value(),
                        section=fact.section.value,
                        verified_at=fact.recorded_at.isoformat(),
                        intake_id=row.id,
                    ),
                )

        return PatientHistory(
            ref=ref,
            hospital_id=hospital_id,
            intakes=summaries,
            carry_forward=sorted(carried.values(), key=lambda c: c.field_id),
        )

    async def register(
        self,
        *,
        hospital_id: str,
        external_mrn: str | None = None,
        abha_address: str | None = None,
        display_name: str | None = None,
        preferred_language: str | None = None,
    ) -> str:
        """Create a patient and return its id. Used to link a guest intake."""
        if not external_mrn and not abha_address:
            raise ValidationError(
                "registering a patient needs either a hospital identifier or an "
                "ABHA address"
            )
        patient_id = self._ids.new_id("pat")
        await self._patients.create(
            patient_id=patient_id,
            hospital_id=hospital_id,
            external_mrn=external_mrn,
            abha_address=abha_address,
            display_name=display_name,
            preferred_language=preferred_language,
        )
        return patient_id
