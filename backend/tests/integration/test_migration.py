"""The migration produces the schema the code expects — §13.1, §13.2.

Every other test in this suite builds its schema with `Base.metadata.create_all`,
which is fast and needs no container, and which proves nothing at all about
`alembic upgrade head`. Those are two different claims: "the metadata is right"
and "the migration produces the metadata". A deployment runs the second one.

So this module runs the real migration against a throwaway database, compares
what came out against the ORM metadata, then seeds the demo hospital on top of it
and renders the worklist — which is the first screen anyone opens, and therefore
the first thing a missing column breaks.

SQLite rather than Postgres, deliberately: the baseline migration is
dialect-neutral (`sa.JSON`, no `JSONB`, no server-side defaults), so it can be
exercised with no container, in CI, on every run. A schema difference that only
Postgres would show is a difference this migration cannot express.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from app.models import Base
from tests.conftest import BACKEND_ROOT, REPO_ROOT


def _alembic_config(url: str) -> Config:
    """An Alembic config pointed at a throwaway database.

    The URL is passed through the environment because `alembic/env.py` reads it
    from `Settings` and never from `alembic.ini` — which is what keeps a
    credential out of the repository, and which this test has to honour rather
    than route around.
    """
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture
def migrated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """An empty database with `alembic upgrade head` run against it.

    Yields the *sync* URL; the async one is derived where it is needed. Two URLs
    for one file is ugly, and less ugly than a second database.
    """
    from app.core.config import get_settings

    path = tmp_path / "migrated.db"
    async_url = f"sqlite+aiosqlite:///{path}"

    monkeypatch.setenv("DATABASE_URL", async_url)
    monkeypatch.setenv("CLINICAL_CONTENT_DIR", str(REPO_ROOT / "clinical"))
    get_settings.cache_clear()
    try:
        command.upgrade(_alembic_config(async_url), "head")
    finally:
        get_settings.cache_clear()
    return f"sqlite:///{path}"


class TestUpgradeFromEmpty:
    def test_every_table_the_orm_declares_exists(self, migrated: str) -> None:
        engine = create_engine(migrated)
        try:
            present = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()

        missing = set(Base.metadata.tables) - present
        assert not missing, (
            f"`alembic upgrade head` did not create {sorted(missing)}. A model was "
            "added without a migration; the tests pass because they build the "
            "schema from metadata and the deployment will not."
        )
        assert "alembic_version" in present

    def test_every_column_the_orm_declares_exists_and_agrees_on_nullability(
        self, migrated: str
    ) -> None:
        """Columns and nullability, per table.

        Types are deliberately not compared. SQLite reports `VARCHAR` for
        `String(64)` and `DATETIME` for `UtcDateTime`, so a type comparison here
        would test the dialect rather than the migration, and would have to be
        loosened until it asserted nothing.
        """
        engine = create_engine(migrated)
        try:
            inspector = inspect(engine)
            differences: list[str] = []
            for name, table in sorted(Base.metadata.tables.items()):
                actual = {c["name"]: c for c in inspector.get_columns(name)}
                for column in table.columns:
                    found = actual.get(column.name)
                    if found is None:
                        differences.append(f"{name}.{column.name} is missing")
                        continue
                    # A primary key is NOT NULL in the database whether or not
                    # the ORM says so, so it is not a difference worth failing.
                    if column.primary_key:
                        continue
                    if bool(found["nullable"]) != bool(column.nullable):
                        differences.append(
                            f"{name}.{column.name} nullable="
                            f"{found['nullable']} in the migration, "
                            f"{column.nullable} in the model"
                        )
                extra = set(actual) - {c.name for c in table.columns}
                differences.extend(f"{name}.{c} exists only in the migration" for c in extra)
        finally:
            engine.dispose()

        assert not differences, "migration and models disagree:\n" + "\n".join(differences)

    def test_the_tenant_scoped_tables_are_indexed_on_hospital_id(
        self, migrated: str
    ) -> None:
        """Every scoped table gets an index on the column every query filters on.

        The tenancy guard in `app/db/tenancy.py` refuses a query without a
        `hospital_id` predicate, which means *every* read of these tables carries
        one. An unindexed column that appears in every WHERE clause is a
        sequential scan per request.
        """
        scoped = sorted(
            name
            for name, table in Base.metadata.tables.items()
            if "hospital_id" in table.columns
        )
        assert scoped, "no tenant-scoped table found; the guard has nothing to guard"

        engine = create_engine(migrated)
        try:
            inspector = inspect(engine)
            unindexed = [
                table
                for table in scoped
                if not any(
                    "hospital_id" in index["column_names"]
                    for index in inspector.get_indexes(table)
                )
            ]
        finally:
            engine.dispose()
        assert not unindexed, f"no hospital_id index on {unindexed}"

    def test_upgrade_is_recorded_at_head(self, migrated: str) -> None:
        """The stamp exists, so a second `upgrade` is a no-op rather than a rerun."""
        from sqlalchemy import text

        engine = create_engine(migrated)
        try:
            with engine.connect() as connection:
                versions = [
                    row[0]
                    for row in connection.execute(text("SELECT version_num FROM alembic_version"))
                ]
        finally:
            engine.dispose()
        # Derived, not hardcoded. A test that names the head revision has to be
        # edited every time a migration is added, and the edit is indistinguishable
        # from someone silencing a genuine failure.
        from alembic.script import ScriptDirectory

        head = ScriptDirectory.from_config(_alembic_config(migrated)).get_current_head()
        assert versions == [head]


class TestSeedingTheMigratedDatabase:
    """§13.2 — a seeded hospital renders a worklist.

    The seeder is the demo. If it works against `create_all` and not against the
    migration, the demo works on the laptop it was written on and nowhere else.
    """

    @pytest.fixture
    def seeded(self, migrated: str) -> dict[str, Any]:
        """Run the seeder against the migrated database, twice.

        Twice because the seeder claims to be idempotent and `make dev` will run
        it on every start.
        """
        from app.services.seed import seed

        async_url = migrated.replace("sqlite://", "sqlite+aiosqlite://")

        async def _run() -> dict[str, Any]:
            engine = create_async_engine(async_url)
            factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            try:
                async with factory() as session:
                    first = await seed(
                        session, terminology_dir=REPO_ROOT / "clinical" / "terminology"
                    )
                    await session.commit()
                async with factory() as session:
                    second = await seed(
                        session, terminology_dir=REPO_ROOT / "clinical" / "terminology"
                    )
                    await session.commit()
                async with factory() as session:
                    rendered = await _worklist(session)
            finally:
                await engine.dispose()
            return {"first": first, "second": second, "worklist": rendered}

        return asyncio.run(_run())

    def test_the_seeder_creates_the_demo_hospital_and_its_intakes(
        self, seeded: dict[str, Any]
    ) -> None:
        from app.services.seed import DEPARTMENTS, HOSPITAL_ID, seeded_intake_ids

        first = seeded["first"]
        assert first["created"] is True
        assert first["hospital_id"] == HOSPITAL_ID
        assert first["departments"] == DEPARTMENTS
        assert first["intakes"] == seeded_intake_ids()
        assert first["terminology_concepts"] > 0

    def test_running_the_seeder_twice_creates_nothing(
        self, seeded: dict[str, Any]
    ) -> None:
        assert seeded["second"]["created"] is False

    def test_the_worklist_renders_every_seeded_intake(
        self, seeded: dict[str, Any]
    ) -> None:
        from app.services.seed import seeded_intake_ids

        worklist = seeded["worklist"]
        assert worklist.total == len(seeded_intake_ids())
        assert {entry.intake_id for entry in worklist.entries} == set(seeded_intake_ids())
        # Arrival order, oldest first. Not triage order — see `domain/worklist.py`.
        arrivals = [(e.arrived_at, e.intake_id) for e in worklist.entries]
        assert arrivals == sorted(arrivals)

    def test_the_red_flag_intake_is_surfaced_for_acknowledgement(
        self, seeded: dict[str, Any]
    ) -> None:
        """The one row a dashboard must not be able to scroll past."""
        from app.domain.worklist import WorklistState

        worklist = seeded["worklist"]
        assert len(worklist.pending_alerts) == 1
        alert = worklist.pending_alerts[0]
        assert alert.state is WorklistState.RED_FLAG_PENDING
        assert alert.unacknowledged_alerts == 1

    def test_the_partial_intake_renders_as_partial_not_as_ready(
        self, seeded: dict[str, Any]
    ) -> None:
        """A partial history is still a history: shown, and shown as partial."""
        from app.domain.worklist import WorklistState

        states = {entry.state for entry in seeded["worklist"].entries}
        assert WorklistState.PARTIAL in states
        assert WorklistState.READY in states


async def _worklist(session: AsyncSession) -> Any:
    """The worklist a staff dashboard would fetch, built the way the API builds it."""
    from datetime import timedelta

    from app.core.clock import SystemClock
    from app.core.config import Settings
    from app.core.content import load_clinical_content
    from app.db.tenancy import tenant_scope
    from app.events.bus import InProcessBus
    from app.repositories.consent import AuditRepository
    from app.repositories.intakes import IntakeRepository
    from app.services.seed import HOSPITAL_ID
    from app.services.worklist import WorklistService

    content = load_clinical_content(Settings(clinical_content_dir=REPO_ROOT / "clinical"))
    service = WorklistService(
        intakes=IntakeRepository(session),
        audit=AuditRepository(session),
        bus=InProcessBus(),
        clock=SystemClock(),
        session=session,
        ingredients=content.ingredients,
    )
    with tenant_scope(HOSPITAL_ID):
        # A wide window: the seeded intakes carry fixed timestamps so the demo
        # reads the same on every machine, and a 24-hour window would empty the
        # list the day after they were written.
        return await service.worklist(
            hospital_id=HOSPITAL_ID, window=timedelta(days=365 * 20)
        )
