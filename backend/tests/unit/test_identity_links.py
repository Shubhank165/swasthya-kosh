"""One patient, several identifiers, one history.

**The assertion in `test_the_phone_and_the_abha_return_the_same_history` is the
whole of the ABHA-linking feature.** Everything else in this file exists to make
that one line meaningful.

The thing worth understanding first is why setting `patients.abha_address` would
not have been enough. Prior visits come from `IntakeRepository.history_for`,
which matches the `(patient_ref_type, patient_ref_value)` an intake was *filed
under* — never `patients.id`, which `intakes.py` writes as NULL at creation. So a
patient with visits filed under a phone HMAC and an ABHA on their chart had two
disjoint histories, and the ABHA one was empty.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.errors import ConflictError
from app.domain.record import PatientRef, PatientRefType
from app.repositories.patients import PatientLinkRepository, PatientRepository
from tests.conftest import HOSPITAL_ID

PHONE_REF = "a1b2c3d4e5f60718a1b2c3d4e5f60718a1b2c3d4e5f60718a1b2c3d4e5f60718"
ABHA = "asha.devi@sbx"
LINKED_AT = datetime(2026, 9, 1, tzinfo=UTC)


def _payload(intake_id: str, ref_type: str, ref_value: str | None, when: str) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "intake_id": intake_id,
        "kiosk_id": "kiosk-1",
        "hospital_id": HOSPITAL_ID,
        "started_at": when,
        "completed_at": when,
        "status": "complete",
        "language": "hi",
        "reporter": "self",
        "department_code": "kayachikitsa",
        "patient_ref": {"type": ref_type, "value": ref_value},
        "turns": [],
        "fields": {
            "chief_complaint": {"value": "fever", "status": "answered"},
        },
        "red_flags": [],
        "engine_version": "test",
        "content_version": "test",
    }


@pytest.fixture
async def two_histories(session: Any, ingest_service: Any) -> None:
    """Two visits by phone, one by OPD card. Nothing links them yet."""
    visits = (
        ("aaaa1111-0000-4000-8000-000000000001", "phone", PHONE_REF, "2026-06-01T09:00:00Z"),
        ("aaaa1111-0000-4000-8000-000000000002", "phone", PHONE_REF, "2026-07-01T09:00:00Z"),
        ("aaaa1111-0000-4000-8000-000000000003", "abha", ABHA, "2026-08-01T09:00:00Z"),
    )
    for intake_id, ref_type, ref_value, when in visits:
        await ingest_service.ingest(
            _payload(intake_id, ref_type, ref_value, when),
            hospital_id=HOSPITAL_ID,
            actor_id="test",
        )


class TestTheLinkTableIsWhatJoinsAHistory:
    async def test_without_a_link_each_identifier_sees_only_its_own(
        self, session: Any, identity_service: Any, two_histories: None
    ) -> None:
        """The state this feature exists to fix, pinned so the fix is visible."""
        by_phone = await identity_service.history(
            PatientRef(type=PatientRefType.PHONE, value=PHONE_REF),
            hospital_id=HOSPITAL_ID,
        )
        by_abha = await identity_service.history(
            PatientRef(type=PatientRefType.ABHA, value=ABHA), hospital_id=HOSPITAL_ID
        )
        assert len(by_phone.intakes) == 2
        assert len(by_abha.intakes) == 1

    async def test_the_phone_and_the_abha_return_the_same_history(
        self, session: Any, identity_service: Any, two_histories: None
    ) -> None:
        """**The feature.** Same intakes, same order, whichever way in."""
        patients = PatientRepository(session)
        links = PatientLinkRepository(session)
        patient = await patients.create(
            patient_id="pat-link-1", hospital_id=HOSPITAL_ID, abha_address=ABHA
        )
        for ref_type, ref_value in (("phone", PHONE_REF), ("abha", ABHA)):
            await links.link(
                link_id=f"lnk-{ref_type}",
                hospital_id=HOSPITAL_ID,
                patient_id=patient.id,
                ref_type=ref_type,
                ref_value=ref_value,
                source="test",
                linked_at=LINKED_AT,
            )

        by_phone = await identity_service.history(
            PatientRef(type=PatientRefType.PHONE, value=PHONE_REF),
            hospital_id=HOSPITAL_ID,
        )
        by_abha = await identity_service.history(
            PatientRef(type=PatientRefType.ABHA, value=ABHA), hospital_id=HOSPITAL_ID
        )

        ids_by_phone = [i["intake_id"] for i in by_phone.intakes]
        ids_by_abha = [i["intake_id"] for i in by_abha.intakes]
        assert len(ids_by_phone) == 3
        assert ids_by_phone == ids_by_abha

    async def test_a_merged_set_is_still_one_chronology(
        self, session: Any, identity_service: Any, two_histories: None
    ) -> None:
        """Newest first across both identifiers, not one list after another."""
        links = PatientLinkRepository(session)
        patients = PatientRepository(session)
        patient = await patients.create(patient_id="pat-link-2", hospital_id=HOSPITAL_ID)
        for ref_type, ref_value in (("phone", PHONE_REF), ("abha", ABHA)):
            await links.link(
                link_id=f"lnk2-{ref_type}",
                hospital_id=HOSPITAL_ID,
                patient_id=patient.id,
                ref_type=ref_type,
                ref_value=ref_value,
                source="test",
                linked_at=LINKED_AT,
            )

        history = await identity_service.history(
            PatientRef(type=PatientRefType.PHONE, value=PHONE_REF),
            hospital_id=HOSPITAL_ID,
        )
        received = [i["received_at"] for i in history.intakes]
        assert received == sorted(received, reverse=True)


class TestTheTableRefusesToMergeTwoPeople:
    async def test_relinking_the_same_pair_is_a_no_op(self, session: Any) -> None:
        links = PatientLinkRepository(session)
        patients = PatientRepository(session)
        patient = await patients.create(patient_id="pat-idem", hospital_id=HOSPITAL_ID)
        now = LINKED_AT
        first = await links.link(
            link_id="lnk-a",
            hospital_id=HOSPITAL_ID,
            patient_id=patient.id,
            ref_type="phone",
            ref_value=PHONE_REF,
            source="test",
            linked_at=now,
        )
        again = await links.link(
            link_id="lnk-b",
            hospital_id=HOSPITAL_ID,
            patient_id=patient.id,
            ref_type="phone",
            ref_value=PHONE_REF,
            source="test",
            linked_at=now,
        )
        assert again.id == first.id

    async def test_repointing_an_identifier_at_another_patient_raises(
        self, session: Any
    ) -> None:
        """Two people sharing a phone, or a mis-keyed ABHA — a human looks.

        Silently repointing would join two patients' histories, which is the
        worst thing this table can do.
        """
        links = PatientLinkRepository(session)
        patients = PatientRepository(session)
        one = await patients.create(patient_id="pat-one", hospital_id=HOSPITAL_ID)
        two = await patients.create(patient_id="pat-two", hospital_id=HOSPITAL_ID)
        now = LINKED_AT
        await links.link(
            link_id="lnk-c",
            hospital_id=HOSPITAL_ID,
            patient_id=one.id,
            ref_type="abha",
            ref_value=ABHA,
            source="test",
            linked_at=now,
        )
        with pytest.raises(ConflictError):
            await links.link(
                link_id="lnk-d",
                hospital_id=HOSPITAL_ID,
                patient_id=two.id,
                ref_type="abha",
                ref_value=ABHA,
                source="test",
                linked_at=now,
            )

    async def test_an_unlinked_reference_expands_to_itself(self, session: Any) -> None:
        """So a caller can expand unconditionally, and an unlinked patient
        behaves exactly as they did before this table existed."""
        links = PatientLinkRepository(session)
        assert await links.aliases_for(
            hospital_id=HOSPITAL_ID, ref_type="phone", ref_value=PHONE_REF
        ) == (("phone", PHONE_REF),)


class TestResolvingAPhoneReference:
    async def test_it_is_not_answered_as_a_failed_abha_lookup(
        self, identity_service: Any, two_histories: None
    ) -> None:
        """`resolve` had no PHONE branch, so a phone reference fell through to
        `abha.verify()` and came back "ABHA address could not be verified" —
        about a phone number."""
        resolved = await identity_service.resolve(
            PatientRef(type=PatientRefType.PHONE, value=PHONE_REF),
            hospital_id=HOSPITAL_ID,
        )
        assert resolved.verified is True
        assert resolved.known_here is True
        assert resolved.source == "app_sign_in"
        assert resolved.notice is None

    async def test_a_phone_nobody_has_used_here_is_verified_but_unknown(
        self, identity_service: Any
    ) -> None:
        resolved = await identity_service.resolve(
            PatientRef(type=PatientRefType.PHONE, value="f" * 64),
            hospital_id=HOSPITAL_ID,
        )
        # Holding the HMAC is the verification — it cannot be built without
        # having passed the OTP — but there is nothing filed under it.
        assert resolved.verified is True
        assert resolved.known_here is False
