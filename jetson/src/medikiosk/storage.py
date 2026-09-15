import hashlib
import hmac
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet

from medikiosk.models import PatientState


class EncryptedSessionStore:
    """Application-layer encrypted SQLite; plaintext patient state is never written."""

    def __init__(self, path: Path, encryption_key: str) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cipher = Fernet(encryption_key.encode("ascii"))
        # Separate key for the lookup HMAC below, derived from the same secret so there is still
        # only one to manage, but domain-separated so it is never the encryption key itself.
        self._lookup_key = hashlib.sha256(
            b"medikiosk.prakriti.subject:" + encryption_key.encode("ascii")
        ).digest()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    encrypted_state BLOB NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS reports "
                "(encounter_id TEXT PRIMARY KEY, encrypted_report BLOB NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS prakriti "
                "(subject TEXT PRIMARY KEY, encrypted_record BLOB NOT NULL, recorded_at TEXT "
                "NOT NULL)"
            )

    def _subject(self, abha_number: str) -> str:
        """Key the Prakriti row by a keyed hash of the ABHA number, not the number itself.

        The row has to be findable by ABHA on a later visit, so the key cannot be random - but a
        health ID sitting in a primary key is a plaintext identifier in a store whose whole point
        is that patient data is never written in the clear. HMAC with the store's own key keeps
        lookup working and keeps the number out of the file; without the key the column is not
        reversible, and it is not guessable by trying all 14-digit numbers either.
        """

        return hmac.new(
            self._lookup_key, abha_number.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def save_prakriti(self, abha_number: str, record: dict) -> None:
        """Store one lifetime Prakriti record. Re-running the questionnaire replaces it."""

        recorded_at = datetime.now(timezone.utc).isoformat()
        stored = {**record, "recorded_at": recorded_at}
        encrypted = self.cipher.encrypt(json.dumps(stored, ensure_ascii=False).encode("utf-8"))
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO prakriti VALUES (?, ?, ?) ON CONFLICT(subject) DO UPDATE SET "
                "encrypted_record = excluded.encrypted_record, "
                "recorded_at = excluded.recorded_at",
                (self._subject(abha_number), encrypted, recorded_at),
            )

    def load_prakriti(self, abha_number: str) -> dict | None:
        """The Prakriti recorded for this ABHA on any previous visit, or None."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT encrypted_record FROM prakriti WHERE subject = ?",
                (self._subject(abha_number),),
            ).fetchone()
        return json.loads(self.cipher.decrypt(row[0])) if row else None

    def save_report(self, encounter_id: str, report: dict) -> None:
        encrypted = self.cipher.encrypt(json.dumps(report, ensure_ascii=False).encode('utf-8'))
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO reports VALUES (?, ?) ON CONFLICT(encounter_id) "
                "DO UPDATE SET encrypted_report = excluded.encrypted_report",
                (encounter_id, encrypted),
            )

    def load_report(self, encounter_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT encrypted_report FROM reports WHERE encounter_id = ?", (encounter_id,)
            ).fetchone()
        return json.loads(self.cipher.decrypt(row[0])) if row else None

    def save(self, session_id: str, state: PatientState) -> None:
        encrypted = self.cipher.encrypt(state.model_dump_json().encode("utf-8"))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions(session_id, encrypted_state, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    encrypted_state = excluded.encrypted_state,
                    updated_at = excluded.updated_at
                """,
                (session_id, encrypted, state.updated_at.isoformat()),
            )

    def load(self, session_id: str) -> PatientState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT encrypted_state FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        payload = self.cipher.decrypt(row[0])
        return PatientState.model_validate_json(payload)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)
