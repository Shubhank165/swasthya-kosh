"""Seed a database with the demo AYUSH facility.

    python scripts/seed.py

Idempotent. Safe to run against an existing database.
"""

from __future__ import annotations

import asyncio
import json

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import session_scope
from app.services.seed import seed


async def main() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=False)
    async with session_scope() as session:
        result = await seed(session, terminology_dir=settings.terminology_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
