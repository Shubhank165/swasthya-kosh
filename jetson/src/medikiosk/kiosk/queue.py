"""The OPD queue the kiosk feeds, and the specialties it can route to.

Two rules shape this module.

A red flag does not mean "front of the queue". Pushing a possible myocardial infarction to
position one of a routine cardiology list still leaves them waiting behind whoever is in the room.
Those patients leave the ordinary queue entirely and land on a review list that staff are expected
to clear, which is what spec §24 asks for.

Ordering is otherwise plain arrival order within a priority band. Anything cleverer - predicted
consultation length, doctor load balancing - would be guessing at hospital operations we have not
observed, and a queue a receptionist cannot predict is a queue they will override.

Specialties are configuration, not code: departments differ per hospital, and a site without a
cardiologist must be able to say so without a release.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet

# Shipped default. A hospital overrides it with its own file; nothing here assumes these exist.
DEFAULT_SPECIALTIES: tuple[str, ...] = (
    "Emergency",
    "General Medicine",
    "Cardiology",
    "Pulmonology",
    "Gastroenterology",
    "Neurology",
    "Orthopaedics",
    "Ophthalmology",
    "ENT",
    "Dermatology",
    "Dentistry",
    "Obstetrics and Gynaecology",
    "Ayush OPD",
)

# Bands, most urgent first. REVIEW is deliberately not a priority level - it is a different list.
BANDS = ("review", "urgent", "routine")


@dataclass(frozen=True)
class QueueEntry:
    id: int
    encounter_id: str
    specialty: str
    band: str
    number: int
    complaint: str | None
    reason: str
    state: str
    created_at: str

    @property
    def needs_review(self) -> bool:
        return self.band == "review"


def load_specialties(path: Path | None = None) -> list[str]:
    """Hospital configuration if present, the shipped list otherwise."""

    if path is not None and path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            names = [s["name"] for s in data.get("specialties", []) if s.get("enabled", True)]
            if names:
                return names
        except (ValueError, KeyError, TypeError):
            pass  # a malformed config must not take the kiosk down; fall back below
    return list(DEFAULT_SPECIALTIES)


def band_for(routing: dict) -> str:
    """Map a report's routing block onto a queue band.

    An emergency is never merely 'high priority'. It leaves the queue.
    """

    priority = (routing or {}).get("priority", "routine")
    if priority == "emergency":
        return "review"
    if priority == "urgent":
        return "urgent"
    return "routine"


class QueueStore:
    """Queue entries, in the same SQLite file style as the rest of the kiosk.

    Holds no clinical detail beyond the complaint line staff need to recognise a patient: the full
    report stays in the encrypted session store, and a waiting-room screen should never be one
    query away from someone's history.
    """

    def __init__(self, path: Path, encryption_key: str | None = None) -> None:
        self.cipher = Fernet(encryption_key.encode("ascii")) if encryption_key else None
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS queue_entries (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    encounter_id  TEXT NOT NULL UNIQUE,
                    specialty     TEXT NOT NULL,
                    band          TEXT NOT NULL,
                    number        INTEGER NOT NULL,
                    complaint     TEXT,
                    reason        TEXT NOT NULL,
                    state         TEXT NOT NULL DEFAULT 'WAITING',
                    created_at    TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS queue_by_state ON queue_entries(state, band)"
            )

    def assign(self, encounter_id: str, report: dict) -> QueueEntry:
        """Place a finished encounter in a queue. Idempotent per encounter."""

        routing = report.get("routing", {})
        specialty = routing.get("queue", "General Medicine")
        band = band_for(routing)
        complaint = (report.get("clinical") or {}).get("complaint")
        reason = routing.get("reason", "")
        if self.cipher:
            complaint = self.cipher.encrypt(json.dumps(complaint).encode())
            reason = self.cipher.encrypt(json.dumps(reason).encode())
        now = datetime.now(timezone.utc).isoformat()
        state = "FINALIZING" if report.get("completion") == "finalizing" else "WAITING"

        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM queue_entries WHERE encounter_id = ?", (encounter_id,)
            ).fetchone()
            if existing is not None:
                return self._row(existing)

            # Numbering runs per specialty per band, so "Cardiology 4" means something to staff.
            (taken,) = connection.execute(
                "SELECT COUNT(*) FROM queue_entries WHERE specialty = ? AND band = ?",
                (specialty, band),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO queue_entries
                    (encounter_id, specialty, band, number, complaint, reason, state, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (encounter_id, specialty, band, taken + 1, complaint, reason, state, now),
            )
            row = connection.execute(
                "SELECT * FROM queue_entries WHERE encounter_id = ?", (encounter_id,)
            ).fetchone()
        return self._row(row)

    def finalizing(self) -> list[QueueEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM queue_entries WHERE state = 'FINALIZING'"
            ).fetchall()
        return [self._row(row) for row in rows]

    def publish(self, encounter_id: str) -> None:
        """Expose a committed encounter without resetting a staff lifecycle change."""
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE queue_entries SET state='WAITING' "
                "WHERE encounter_id=? AND state='FINALIZING'",
                (encounter_id,),
            )

    def waiting(self) -> list[QueueEntry]:
        """Everyone still waiting, review cases first, then arrival order within each band."""

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM queue_entries WHERE state = 'WAITING' ORDER BY id"
            ).fetchall()
        entries = [self._row(row) for row in rows]
        return sorted(entries, key=lambda e: (BANDS.index(e.band), e.id))

    def set_state(self, encounter_id: str, state: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE queue_entries SET state = ? WHERE encounter_id = ?",
                (state, encounter_id),
            )

    def get(self, encounter_id: str) -> QueueEntry | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM queue_entries WHERE encounter_id = ?", (encounter_id,)
            ).fetchone()
        return self._row(row) if row is not None else None

    def _row(self, row: sqlite3.Row) -> QueueEntry:
        def decode(value):
            if isinstance(value, bytes):
                if self.cipher is None:
                    raise ValueError("Queue encryption key required")
                return json.loads(self.cipher.decrypt(value))
            return value  # Historical plaintext is readable, never rewritten implicitly.

        return QueueEntry(
            id=row["id"],
            encounter_id=row["encounter_id"],
            specialty=row["specialty"],
            band=row["band"],
            number=row["number"],
            complaint=decode(row["complaint"]),
            reason=decode(row["reason"]),
            state=row["state"],
            created_at=row["created_at"],
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection
