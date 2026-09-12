"""The seeded demo: sign in by phone, see two visits; link ABHA, see three.

This is the demo the ABHA work exists to make possible, and the reason it is a
test is that the interesting half is invisible on screen. `patients.abha_address`
being set looks like the feature and is not: history is keyed on the reference
an intake was filed under, so without the link rows the ABHA answer is empty and
nothing about the screen says why.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.tenancy import tenant_scope
from app.domain.record import PatientRef, PatientRefType
from app.repositories.patients import PatientLinkRepository
from app.services.patient_auth import phone_ref
from app.services.seed import DEMO_ABHA, DEMO_PHONE, seed
from tests.conftest import HOSPITAL_ID

PEPPER = "a-test-pepper-that-is-not-the-deployment-one"


@pytest.fixture
async def session(engine: Any) -> AsyncIterator[AsyncSession]:
    """A session with **no hospital yet**, overriding the shared fixture.

    `seed()` short-circuits on an existing hospital — deliberately, so running
    it twice is a no-op — and the usual `session` fixture creates one. Seeding
    into that returns `{"created": False}` and writes nothing, which is a test
    that passes while proving nothing at all.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as opened:
        with tenant_scope(HOSPITAL_ID):
            yield opened
        await opened.rollback()


class TestTheSeededDemo:
    async def test_the_phone_sees_the_visits_taken_in_the_app(
        self, session: Any, identity_service: Any
    ) -> None:
        await seed(session, patient_ref_pepper=PEPPER)
        history = await identity_service.history(
            PatientRef(
                type=PatientRefType.PHONE, value=phone_ref(DEMO_PHONE, pepper=PEPPER)
            ),
            hospital_id=HOSPITAL_ID,
        )
        # Two app visits, plus the kiosk visit filed under the same patient's
        # UHID — the link rows are what bring that third one in.
        assert len(history.intakes) == 3

    async def test_the_abha_sees_the_same_visits(
        self, session: Any, identity_service: Any
    ) -> None:
        """The one assertion the whole feature reduces to."""
        await seed(session, patient_ref_pepper=PEPPER)
        by_phone = await identity_service.history(
            PatientRef(
                type=PatientRefType.PHONE, value=phone_ref(DEMO_PHONE, pepper=PEPPER)
            ),
            hospital_id=HOSPITAL_ID,
        )
        by_abha = await identity_service.history(
            PatientRef(type=PatientRefType.ABHA, value=DEMO_ABHA),
            hospital_id=HOSPITAL_ID,
        )
        assert [i["intake_id"] for i in by_abha.intakes] == [
            i["intake_id"] for i in by_phone.intakes
        ]

    async def test_the_older_app_visits_come_last(
        self, session: Any, identity_service: Any
    ) -> None:
        """Merged, not concatenated."""
        await seed(session, patient_ref_pepper=PEPPER)
        history = await identity_service.history(
            PatientRef(type=PatientRefType.ABHA, value=DEMO_ABHA),
            hospital_id=HOSPITAL_ID,
        )
        received = [i["received_at"] for i in history.intakes]
        assert received == sorted(received, reverse=True)


class TestTheSeedNeverWritesAPhoneNumber:
    async def test_the_stored_reference_is_a_peppered_digest(
        self, session: Any
    ) -> None:
        await seed(session, patient_ref_pepper=PEPPER)
        links = PatientLinkRepository(session)
        rows = await links.for_patient(
            hospital_id=HOSPITAL_ID, patient_id="pat_seed_0001"
        )
        phone_rows = [row for row in rows if row.ref_type == "phone"]
        assert len(phone_rows) == 1
        value = phone_rows[0].ref_value
        assert re.fullmatch(r"[0-9a-f]{64}", value)
        assert DEMO_PHONE not in value

    async def test_the_digest_is_not_a_constant_in_the_source(
        self, session: Any
    ) -> None:
        """A hardcoded digest is wrong on every deployment with a different
        pepper, and the failure is silent: a patient whose history nobody can
        reach. So the value must actually depend on the pepper."""
        await seed(session, patient_ref_pepper=PEPPER)
        links = PatientLinkRepository(session)
        rows = await links.for_patient(
            hospital_id=HOSPITAL_ID, patient_id="pat_seed_0001"
        )
        stored = next(row.ref_value for row in rows if row.ref_type == "phone")
        assert stored == phone_ref(DEMO_PHONE, pepper=PEPPER)
        assert stored != phone_ref(DEMO_PHONE, pepper="a-different-pepper")


class TestWithoutAPepper:
    async def test_it_completes_and_says_the_phone_half_was_skipped(
        self, session: Any
    ) -> None:
        """`phone_ref` raises without a pepper, by design. The seeder must not
        propagate that — the kiosk demo does not need the app half."""
        result = await seed(session)
        assert result["created"] is True
        assert result["phone_linked"] is False
        assert result["demo_phone"] is None
        assert len(result["intakes"]) == 4

    async def test_the_abha_link_still_lands(
        self, session: Any, identity_service: Any
    ) -> None:
        await seed(session)
        history = await identity_service.history(
            PatientRef(type=PatientRefType.ABHA, value=DEMO_ABHA),
            hospital_id=HOSPITAL_ID,
        )
        # The kiosk visit, reached through the UHID the ABHA is linked to.
        assert len(history.intakes) == 1
