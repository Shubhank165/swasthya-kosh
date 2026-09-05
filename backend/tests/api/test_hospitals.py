"""The hospital picker — 2/3 §5 screen 2, §12."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import HOSPITAL_ID


@pytest.fixture
async def seeded(engine: Any) -> None:
    """Hospital rows, committed.

    `app_client` opens its own session per request, so rows written by the
    `session` fixture and rolled back at teardown are not visible to it. This
    writes through the same engine and commits.
    """
    from tests.conftest import _create_hospitals

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as opened:
        await _create_hospitals(opened)
        await opened.commit()


class TestListingHospitals:
    def test_it_is_reachable_without_a_credential(self, app_client: Any) -> None:
        """It is the list a patient chooses from before they have anything to
        authenticate as."""
        assert app_client.get("/api/v1/hospitals").status_code == 200

    def test_the_seeded_hospital_appears_with_its_departments(
        self, app_client: Any, seeded: Any
    ) -> None:
        body = app_client.get("/api/v1/hospitals").json()
        ours = next(h for h in body["hospitals"] if h["hospital_id"] == HOSPITAL_ID)
        assert ours["departments"]
        assert all(d["code"] and d["display"] for d in ours["departments"])

    def test_it_holds_nothing_a_signboard_would_not(
        self, app_client: Any, seeded: Any
    ) -> None:
        """Name, location, timezone, language and departments. No counts, no
        patients, no clinical anything — which is why it needs no credential."""
        body = app_client.get("/api/v1/hospitals").json()
        for hospital in body["hospitals"]:
            assert set(hospital) == {
                "hospital_id", "display_name", "location", "timezone",
                "default_language", "departments",
            }
