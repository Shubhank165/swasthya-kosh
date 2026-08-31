"""Seed a database with the demo AYUSH facility.

    uv run python scripts/seed.py

Idempotent. Safe to run against an existing database.
"""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import session_scope
from app.services.seed import seed_facility


async def main() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=False)
    async with session_scope() as session:
        counts = await seed_facility(session, settings=settings)
    print(
        "seeded: "
        + ", ".join(f"{value} {key}" for key, value in counts.items() if value)
        or "seeded: nothing new"
    )


if __name__ == "__main__":
    asyncio.run(main())
