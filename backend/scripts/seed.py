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
        result = await seed(
            session,
            terminology_dir=settings.terminology_dir,
            patient_ref_pepper=settings.patient_ref_pepper,
        )
    print(json.dumps(result, indent=2))
    if result.get("created"):
        if result.get("phone_linked"):
            # The number, not the reference: the reference identifies a patient.
            print(
                f"\nDemo patient: sign in to the app with {result['demo_phone']}, "
                f"then link ABHA {result['demo_abha']} to see the OPD-card visit too."
            )
        else:
            print(
                "\nPATIENT_REF_PEPPER is not set, so no phone-linked visits were "
                "seeded. The app half of the demo needs it; set it and re-seed."
            )


if __name__ == "__main__":
    asyncio.run(main())
