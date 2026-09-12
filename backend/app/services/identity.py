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
from app.domain.record import (
    CanonicalRecord,
    FieldStatus,
    PatientRef,
    PatientRefType,
)
from app.repositories.intakes import IntakeRepository
from app.repositories.patients import PatientLinkRepository, PatientRepository

logger = get_logger(__name__)

#: What the Jetson pre-loads. The doctor's confirmed conditions, medicines and
#: allergies — so the next intake can ask "our record shows diabetes, still
#: correct?" instead of starting from nothing.
CARRY_FORWARD_SECTIONS: frozenset[Section] = frozenset(
    {Section.PAST_MEDICAL, Section.MEDICATIONS, Section.ALLERGIES}
)


def _complaint_of(record: CanonicalRecord) -> str | None:
    """What the patient said was wrong, in their own words where they exist.

    `original_text` first and the coded value second, which is the order used
    everywhere a human reads a fact: "seene mein dard" is what the patient said
    and `chest_pain` is what it was coded as, and only one of those is worth
    showing back to them.

    Returns `None` rather than a placeholder when the field is not answered — a
    visit with no recorded complaint is a real state, and "Unknown" printed in
    a list of a patient's own visits reads like the record was lost.
    """
    for fact in record.live_facts():
        if fact.field_id != "chief_complaint":
            continue
        if fact.status is not FieldStatus.ANSWERED:
            return None
        return fact.original_text or fact.rendered_value()
    return None


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
        links: PatientLinkRepository | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        self._patients = patients
        self._intakes = intakes
        self._abha = abha
        self._clock = clock
        self._ids = ids
        self._links = links
        self._labels = labels or {}

    async def _refs_for(self, ref: PatientRef, *, hospital_id: str) -> tuple[tuple[str, str], ...]:
        """Every reference that resolves to the same person as `ref`.

        Without a link repository — and there is none in the older call sites —
        this is `ref` alone, which is exactly the behaviour before the link
        table existed. History never silently widens because a dependency
        happened to be wired.
        """
        assert ref.value is not None
        me = ((ref.type.value, ref.value),)
        if self._links is None:
            return me
        return await self._links.aliases_for(
            hospital_id=hospital_id, ref_type=ref.type.value, ref_value=ref.value
        )

    async def resolve(
        self,
        ref: PatientRef,
        *,
        hospital_id: str,
        link_to_ref: PatientRef | None = None,
    ) -> ResolvedPatient:
        """Identify a patient, without ever requiring that identification succeed.

        A failed ABHA lookup does not fail the request. It comes back
        unverified, and the intake proceeds as a guest — the alternative is
        turning someone away because a government API was down.

        `link_to_ref` records that `ref` and that reference are the same person.
        `POST /patients/me/abha` is the only caller: it is the one place where
        an ABHA address and the phone the patient signed in with are both in
        hand at once, and therefore the only honest place to assert the edge
        between them. The link is written **only when the ABHA verified** — an
        unproven identifier joined to a real history is how one patient reads
        another's.
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

        if ref.type is PatientRefType.PHONE:
            # There was no branch for this, so a phone ref fell through to
            # `self._abha.verify()` and came back "ABHA address could not be
            # verified" — about a phone number. Nothing in the app hits
            # `/patients/resolve`, which is why it went unnoticed, but the
            # endpoint accepts `{"type": "phone"}` and answered nonsense.
            #
            # The value is the peppered HMAC the app's sign-in issued, and
            # possessing it *is* the verification: it cannot be constructed
            # without having passed the OTP.
            assert ref.value is not None
            patient_id = None
            if self._links is not None:
                link = await self._links.get(
                    hospital_id=hospital_id,
                    ref_type=ref.type.value,
                    ref_value=ref.value,
                )
                patient_id = link.patient_id if link else None
            refs = await self._refs_for(ref, hospital_id=hospital_id)
            rows = await self._intakes.history_for(
                hospital_id=hospital_id, refs=refs, limit=1
            )
            return ResolvedPatient(
                ref=ref,
                patient_id=patient_id,
                verified=True,
                known_here=bool(rows) or patient_id is not None,
                source="app_sign_in",
            )

        assert ref.value is not None
        result = await self._abha.verify(ref.value)
        row = await self._patients.by_abha(hospital_id=hospital_id, abha_address=ref.value)
        linked_patient_id = None
        if row is None and self._links is not None:
            # `patients.abha_address` says which ABHA is on the chart. The link
            # table says which references have ever resolved here, and an ABHA
            # linked after registration is only in the second.
            link = await self._links.get(
                hospital_id=hospital_id, ref_type=ref.type.value, ref_value=ref.value
            )
            linked_patient_id = link.patient_id if link else None
        if result is None:
            return ResolvedPatient(
                ref=ref,
                patient_id=row.id if row else linked_patient_id,
                verified=False,
                known_here=row is not None or linked_patient_id is not None,
                source=self._abha.name,
                notice="ABHA address could not be verified. Intake may proceed as guest.",
            )
        verified = bool(result.get("verified"))
        patient_id = row.id if row else linked_patient_id
        if verified and link_to_ref is not None:
            patient_id = await self._join(
                hospital_id=hospital_id,
                patient_id=patient_id,
                abha_address=ref.value,
                refs=(ref, link_to_ref),
            )
        return ResolvedPatient(
            ref=ref,
            patient_id=patient_id,
            verified=verified,
            known_here=row is not None or linked_patient_id is not None,
            # `"mock"` travels all the way to the client. A mocked government
            # integration is never presented as a live one.
            source=str(result.get("source", self._abha.name)),
            notice=result.get("notice"),
        )

    async def _join(
        self,
        *,
        hospital_id: str,
        patient_id: str | None,
        abha_address: str | None,
        refs: tuple[PatientRef, ...],
    ) -> str | None:
        """Record that every reference in `refs` is the same person.

        A link needs something to point at, so when neither reference is
        attached to a patient yet this creates the thin identity row that
        anchors them. That row is the hospital's record that these identifiers
        belong together — not demographics, which the HMIS owns — and it is
        created here rather than at sign-in because this is the first moment
        anything is known beyond a phone number.

        Raises through `PatientLinkRepository.link` if one of these references
        already resolves to somebody else. Two people sharing a phone, or a
        mis-keyed ABHA address, are both things a human must look at; merging
        them quietly would join two patients' histories.
        """
        if self._links is None:
            return patient_id

        if patient_id is None:
            for candidate in refs:
                if candidate.value is None:
                    continue
                link = await self._links.get(
                    hospital_id=hospital_id,
                    ref_type=candidate.type.value,
                    ref_value=candidate.value,
                )
                if link is not None and link.patient_id is not None:
                    patient_id = link.patient_id
                    break

        if patient_id is None:
            created = await self._patients.create(
                patient_id=self._ids.new_id("pat"),
                hospital_id=hospital_id,
                abha_address=abha_address,
            )
            patient_id = created.id

        now = self._clock.now()
        for candidate in refs:
            if candidate.value is None:
                continue
            await self._links.link(
                link_id=self._ids.new_id("lnk"),
                hospital_id=hospital_id,
                patient_id=patient_id,
                ref_type=candidate.type.value,
                ref_value=candidate.value,
                source="abha_link",
                linked_at=now,
            )
        return patient_id

    async def history(
        self, ref: PatientRef, *, hospital_id: str, limit: int = 20
    ) -> PatientHistory:
        """Prior intakes, and what the Jetson should pre-load."""
        if ref.type is PatientRefType.GUEST or ref.value is None:
            # A guest has no history by construction. Returning an empty result
            # rather than an error keeps the kiosk's flow identical either way.
            return PatientHistory(ref=ref, hospital_id=hospital_id)

        # The reference the caller holds, plus every other one that resolves to
        # the same person. This is the line that makes "link my ABHA and see my
        # app visits" work; without it the two histories never meet.
        refs = await self._refs_for(ref, hospital_id=hospital_id)
        rows = await self._intakes.history_for(
            hospital_id=hospital_id, refs=refs, limit=limit
        )
        # `complaint` is filled in below, from the record each row's
        # carry-forward pass already loads. Without it a patient's own list of
        # visits reads "6 September, Kayachikitsa" and says nothing about which
        # visit that was.
        summaries = [
            {
                "intake_id": row.id,
                "status": row.status,
                "language": row.language,
                "department_code": row.department_code,
                "received_at": row.received_at.isoformat(),
                "seen_at": row.seen_at.isoformat() if row.seen_at else None,
                "complaint": None,
            }
            for row in rows
        ]
        by_intake = {summary["intake_id"]: summary for summary in summaries}

        carried: dict[str, CarriedFact] = {}
        for row in rows:
            record = await self._intakes.load(hospital_id=hospital_id, intake_id=row.id)
            by_intake[row.id]["complaint"] = _complaint_of(record)
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
