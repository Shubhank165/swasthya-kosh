"""A disposable backend for the dashboard's end-to-end journey — 3/3 §11.

Starts the **real application** — the real routers, the real guards, the real
report builder — against a throwaway SQLite file, seeds the demo facility, and
ingests two intakes: one ordinary and one that fired a red-flag criterion on the
device.

Deliberately not a mock server. The point of §11 item 7 is that the journey
works against the backend, and a journey run against a hand-written stub proves
only that the stub matches the test's idea of the API.

    python scripts/e2e_backend.py --port 8123 --db /tmp/e2e.sqlite

It exits non-zero if seeding fails, so a CI run cannot proceed against an empty
database and report a green journey over an empty worklist.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = BACKEND_ROOT / "tests" / "fixtures" / "kiosk" / "0.1.json"

#: The token `.env.example` gives the demo kiosk. Bound to one hospital by the
#: backend, which is the whole point of a kiosk token.
KIOSK_TOKEN = "test-kiosk-token"
HOSPITAL_ID = "aiia-delhi"


def configure(database_url: str) -> None:
    """Point the app at the throwaway database before anything imports settings."""
    os.environ.update(
        {
            "DATABASE_URL": database_url,
            "ENVIRONMENT": "development",
            "ALLOW_HEADER_AUTH": "true",
            "DEMO_MODE": "false",
            "KIOSK_TOKENS": json.dumps({KIOSK_TOKEN: HOSPITAL_ID}),
            "LOG_JSON": "false",
            "LOG_LEVEL": "warning",
        }
    )


async def prepare() -> None:
    """Create the schema, seed the facility, and ingest two intakes."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from app import db as db_module
    from app.core.config import get_settings
    from app.db.tenancy import unscoped
    from app.models.base import Base
    from app.services.seed import seed

    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    async with engine.begin() as connection:
        # `create_all` rather than alembic: this database exists for the length
        # of one test run, and running migrations here would make the journey
        # fail for reasons that have nothing to do with the dashboard.
        await connection.run_sync(Base.metadata.create_all)
    db_module.configure(engine)

    async with db_module.session_scope() as session:
        with unscoped():
            await seed(session, terminology_dir=settings.terminology_dir)

    await _ingest_fixtures()


async def _ingest_fixtures() -> None:
    from app.api.deps import reset_providers
    from app.core.clock import SystemClock
    from app.core.ids import UuidIdFactory
    from app.db import session_scope
    from app.db.tenancy import tenant_scope
    from app.events.bus import get_event_bus
    from app.repositories.consent import AuditRepository, IngestRawRepository
    from app.repositories.intakes import IntakeRepository
    from app.services.ingest import IngestService
    from app.adapters.registry import build_providers
    from app.core.config import get_settings

    reset_providers()
    settings = get_settings()
    providers = build_providers(settings)
    bus = await get_event_bus()

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    flagged = copy.deepcopy(payload)
    flagged["intake_id"] = "8d1d8b0e-3d6f-4a52-9b1a-2f0a0c0d0e77"
    flagged["status"] = "aborted_red_flag"
    flagged["red_flags"] = [
        {
            "rule_id": "gi_bleeding_suspected",
            "fired_at_turn": 4,
            "criteria_met": ["haematemesis"],
            "severity": "critical",
            "label": "Urgent clinical review criterion triggered",
        }
    ]

    for body in (payload, flagged):
        async with session_scope() as session:
            with tenant_scope(HOSPITAL_ID):
                service = IngestService(
                    intakes=IntakeRepository(session),
                    raw=IngestRawRepository(session),
                    audit=AuditRepository(session),
                    bus=bus,
                    clock=SystemClock(),
                    ids=UuidIdFactory(),
                    repair_provider=providers.repair,
                    repair_max_attempts=settings.repair_max_attempts,
                )
                result = await service.ingest(
                    body, hospital_id=HOSPITAL_ID, actor_id="e2e-seed"
                )
                print(f"seeded intake {result.intake_id} ({result.status})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--db", default="/tmp/medikiosk-e2e.sqlite")
    arguments = parser.parse_args()

    database = Path(arguments.db)
    database.unlink(missing_ok=True)
    configure(f"sqlite+aiosqlite:///{database}")

    asyncio.run(prepare())

    import uvicorn

    from app.main import create_app

    uvicorn.run(create_app(), host="127.0.0.1", port=arguments.port, log_level="warning")


if __name__ == "__main__":
    main()
