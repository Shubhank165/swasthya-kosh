"""Tenancy — §13.8.

**A query without a hospital filter fails.**

Not "is discouraged", not "is caught in review" — fails, at the point of
execution, with an exception naming the tables it touched. One hospital seeing
another's OPD is a reportable breach, and it is the kind of bug that looks
exactly like a working feature until somebody notices.

Three claims here, and they need all three:

1. Every tenant-scoped table actually carries `hospital_id` (schema).
2. A query that omits the filter raises (the guard).
3. A repository given hospital A's scope cannot read hospital B's rows
   (behaviour).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from app.db.tenancy import (
    MissingTenantFilter,
    NoTenantContext,
    current_tenant,
    require_tenant,
    tenant_scope,
    unscoped,
)
from app.models import Base
from app.models.clinical import TENANT_COLUMN, TENANT_EXEMPT_TABLES, IntakeRecord
from tests.conftest import HOSPITAL_ID, OTHER_HOSPITAL_ID


class TestTheSchemaSupportsIt:
    def test_every_table_is_scoped_or_explicitly_exempt(self) -> None:
        """No table gets to be neither.

        A new table with no `hospital_id` and no entry in the exemption set
        fails here — which forces the author to decide, in a review, whether it
        holds patient data.
        """
        unscoped_tables = sorted(
            name
            for name, table in Base.metadata.tables.items()
            if name not in TENANT_EXEMPT_TABLES and TENANT_COLUMN not in table.columns
        )
        assert unscoped_tables == [], (
            f"tables with neither a {TENANT_COLUMN} column nor an exemption: "
            f"{unscoped_tables}"
        )

    def test_exemptions_are_what_they_claim_to_be(self) -> None:
        """The exemption set holds what it claims to hold.

        Two kinds of thing qualify. `hospitals` is the tenant list and the
        terminology tables are code systems, which no hospital owns. The two
        patient-auth tables are the second kind: a person signs into the app
        before choosing a hospital, so their sign-in cannot be scoped to one.

        Anything else appearing here would be clinical data quietly excused from
        scoping, which is why this is asserted as an exact set rather than a
        subset — adding a table to the exemption list has to be a visible edit
        in a file called `test_tenancy.py`.
        """
        assert frozenset(
            {
                "hospitals",
                "terminology_concepts",
                "terminology_mappings",
                "alembic_version",
                "otp_challenges",
                "patient_sessions",
            }
        ) == TENANT_EXEMPT_TABLES

    def test_no_exempt_table_holds_a_plaintext_identifier(self) -> None:
        """The patient-auth exemptions are only defensible because they are opaque.

        `otp_challenges` and `patient_sessions` sit outside the tenant guard, so
        a query bug cannot be caught there. What makes that acceptable is that
        neither holds a phone number, a code or a usable token — the phone is a
        peppered HMAC and the rest are hashes.

        This asserts the column names that would betray a regression: somebody
        adding `phone` or `token` to either table for debugging convenience.
        """
        forbidden = {"phone", "phone_number", "msisdn", "code", "token", "otp"}
        for name in ("otp_challenges", "patient_sessions"):
            columns = set(Base.metadata.tables[name].columns.keys())
            assert not (columns & forbidden), (
                f"{name} has a plaintext identifier column: "
                f"{sorted(columns & forbidden)}"
            )

    def test_the_tenant_column_is_indexed_everywhere(self) -> None:
        """Every scoped query filters on it, so every scoped table indexes it."""
        unindexed = []
        for name, table in Base.metadata.tables.items():
            if name in TENANT_EXEMPT_TABLES or TENANT_COLUMN not in table.columns:
                continue
            column = table.columns[TENANT_COLUMN]
            indexed = column.index or any(
                TENANT_COLUMN in {c.name for c in index.columns} for index in table.indexes
            )
            if not indexed:
                unindexed.append(name)
        assert unindexed == []


class TestTheGuardFires:
    async def test_a_query_without_the_filter_raises(
        self, unscoped_session_factory: Any
    ) -> None:
        """The load-bearing assertion.

        A SELECT against a scoped table with no `hospital_id` predicate does not
        return the wrong rows — it does not return at all.
        """
        async with unscoped_session_factory() as session:
            with tenant_scope(HOSPITAL_ID), pytest.raises(MissingTenantFilter) as caught:
                await session.execute(select(IntakeRecord))
        assert "intakes" in caught.value.details["tables"]

    async def test_a_query_with_the_filter_is_allowed(
        self, unscoped_session_factory: Any
    ) -> None:
        async with unscoped_session_factory() as session:
            with tenant_scope(HOSPITAL_ID):
                result = await session.execute(
                    select(IntakeRecord).where(IntakeRecord.hospital_id == HOSPITAL_ID)
                )
        assert result.scalars().all() == []

    async def test_the_filter_is_found_inside_a_compound_predicate(
        self, unscoped_session_factory: Any
    ) -> None:
        """A nested WHERE still counts. The guard walks the clause tree."""
        async with unscoped_session_factory() as session:
            with tenant_scope(HOSPITAL_ID):
                await session.execute(
                    select(IntakeRecord).where(
                        (IntakeRecord.status == "complete")
                        & (IntakeRecord.hospital_id == HOSPITAL_ID)
                    )
                )

    async def test_an_update_without_the_filter_raises(
        self, unscoped_session_factory: Any
    ) -> None:
        """A write is worse than a read, and was the case that got through.

        `Update` and `Delete` carry a single target table and have no
        `get_final_froms`, so the guard raised an `AttributeError` on them
        instead of `MissingTenantFilter` — the statement was still refused, but
        for a reason nobody would read as a tenancy problem, and one line of
        defensive `except Exception` anywhere above it would have turned the
        refusal into a silent cross-hospital write.
        """
        from sqlalchemy import update

        async with unscoped_session_factory() as session:
            with tenant_scope(HOSPITAL_ID), pytest.raises(MissingTenantFilter) as caught:
                await session.execute(update(IntakeRecord).values(status="complete"))
        assert "intakes" in caught.value.details["tables"]

    async def test_a_delete_without_the_filter_raises(
        self, unscoped_session_factory: Any
    ) -> None:
        from sqlalchemy import delete

        async with unscoped_session_factory() as session:
            with tenant_scope(HOSPITAL_ID), pytest.raises(MissingTenantFilter) as caught:
                await session.execute(delete(IntakeRecord))
        assert "intakes" in caught.value.details["tables"]

    async def test_a_scoped_update_is_allowed(
        self, unscoped_session_factory: Any
    ) -> None:
        from sqlalchemy import update

        async with unscoped_session_factory() as session:
            with tenant_scope(HOSPITAL_ID):
                await session.execute(
                    update(IntakeRecord)
                    .where(IntakeRecord.hospital_id == HOSPITAL_ID)
                    .values(status="complete")
                )

    async def test_a_scoped_delete_is_allowed(
        self, unscoped_session_factory: Any
    ) -> None:
        from sqlalchemy import delete

        async with unscoped_session_factory() as session:
            with tenant_scope(HOSPITAL_ID):
                await session.execute(
                    delete(IntakeRecord).where(IntakeRecord.hospital_id == HOSPITAL_ID)
                )

    async def test_reference_tables_need_no_filter(
        self, unscoped_session_factory: Any
    ) -> None:
        """A code system does not belong to a hospital."""
        from app.models.clinical import TerminologyConcept

        async with unscoped_session_factory() as session:
            with tenant_scope(HOSPITAL_ID):
                await session.execute(select(TerminologyConcept))

    async def test_unscoped_is_the_only_escape(
        self, unscoped_session_factory: Any
    ) -> None:
        """`unscoped()` exists for migrations and the seeder, and is explicit."""
        async with unscoped_session_factory() as session:
            with tenant_scope(HOSPITAL_ID), unscoped():
                await session.execute(select(IntakeRecord))


class TestTheContextIsRequired:
    def test_no_tenant_in_scope_raises(self) -> None:
        assert current_tenant() is None
        with pytest.raises(NoTenantContext):
            require_tenant()

    def test_scope_is_restored_after_the_block(self) -> None:
        with tenant_scope(HOSPITAL_ID):
            assert require_tenant() == HOSPITAL_ID
            with tenant_scope(OTHER_HOSPITAL_ID):
                assert require_tenant() == OTHER_HOSPITAL_ID
            assert require_tenant() == HOSPITAL_ID
        assert current_tenant() is None

    def test_scope_is_restored_after_an_exception(self) -> None:
        with pytest.raises(RuntimeError), tenant_scope(HOSPITAL_ID):
            raise RuntimeError("boom")
        assert current_tenant() is None


class TestIsolationInPractice:
    async def test_one_hospital_cannot_read_anothers_intake(
        self,
        session: Any,
        ingest_service: Any,
        kiosk_payload: dict[str, Any],
    ) -> None:
        """The behaviour the whole mechanism exists for."""
        from app.core.errors import NotFoundError
        from app.repositories.intakes import IntakeRepository

        result = await ingest_service.ingest(
            kiosk_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        repository = IntakeRepository(session)

        assert await repository.exists(
            hospital_id=HOSPITAL_ID, intake_id=result.intake_id
        )
        with tenant_scope(OTHER_HOSPITAL_ID):
            assert not await repository.exists(
                hospital_id=OTHER_HOSPITAL_ID, intake_id=result.intake_id
            )
            with pytest.raises(NotFoundError):
                await repository.load(
                    hospital_id=OTHER_HOSPITAL_ID, intake_id=result.intake_id
                )

    async def test_the_body_cannot_override_the_tokens_hospital(
        self, session: Any, ingest_service: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        """A device claiming another hospital is ignored, not obeyed.

        The kiosk's credential is scoped to one hospital, and that scope wins
        over anything in the payload. A misconfigured device must not be able to
        write a row into somebody else's data.
        """
        from app.repositories.intakes import IntakeRepository

        payload = {**kiosk_payload, "hospital_id": OTHER_HOSPITAL_ID}
        result = await ingest_service.ingest(
            payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        row = await IntakeRepository(session).get_row(
            hospital_id=HOSPITAL_ID, intake_id=result.intake_id
        )
        assert row.hospital_id == HOSPITAL_ID

    async def test_the_worklist_is_scoped(
        self, session: Any, ingest_service: Any, worklist_service: Any,
        kiosk_payload: dict[str, Any],
    ) -> None:
        await ingest_service.ingest(
            kiosk_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        mine = await worklist_service.worklist(hospital_id=HOSPITAL_ID)
        assert mine.total == 1
        with tenant_scope(OTHER_HOSPITAL_ID):
            theirs = await worklist_service.worklist(hospital_id=OTHER_HOSPITAL_ID)
        assert theirs.total == 0
