"""Deterministic clinical differential engine (entropy/FSM over a SQLite knowledge base).

Vendored from the standalone MediKiosk engine. Intra-package imports were rewritten to be
package-relative; the logic is unchanged. Used here for the differential and FHIR output on
the doctor's sheet - the question flow itself stays with the multilingual voice interview.
"""

from __future__ import annotations

import sqlite3
import threading

_seed_lock = threading.Lock()


def ensure_database() -> None:
    """Build the knowledge base if it is not there yet.

    The database is a build artefact, not source: `.gitignore` excludes `*.db` so that patient
    records can never be committed by accident, which means a fresh clone has no knowledge base
    and every differential silently returns nothing. Seeding it on first use keeps that safety
    rule and still leaves the engine working straight after `git clone`.
    """

    from medikiosk.engine.config import DB_PATH

    with _seed_lock:
        try:
            with sqlite3.connect(DB_PATH) as connection:
                connection.execute('SELECT 1 FROM nodes LIMIT 1')
            return
        except sqlite3.DatabaseError:
            pass  # missing, empty, or half-written - rebuild it below

        from medikiosk.engine.master_clinical_database import seed_all

        seed_all()
