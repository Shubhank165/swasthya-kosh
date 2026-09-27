import hashlib
import hmac
import json
import sqlite3
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
        # The domain string still names a table that is gone. It stays exactly as it is: it feeds
        # the resume-token HMAC as well, and changing it would invalidate every session a kiosk
        # in the field is currently holding.
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

    def save_workflow(self, session_id: str, payload: dict, resume_token: str) -> None:
        if payload.get("guard", {}).get("session_id") != session_id or len(resume_token) < 32:
            raise ValueError("Invalid workflow ownership")
        encrypted = self.cipher.encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        token_hash = hmac.new(
            self._lookup_key, b"resume:" + resume_token.encode(), hashlib.sha256
        ).hexdigest()
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS workflows "
                "(session_id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, "
                "payload BLOB NOT NULL)"
            )
            connection.execute(
                "INSERT INTO workflows VALUES (?, ?, ?) ON CONFLICT(session_id) "
                "DO UPDATE SET payload=excluded.payload, token_hash=excluded.token_hash",
                (session_id, token_hash, encrypted),
            )

    def restart_workflow(self, retired: dict, old_token: str, fresh: dict, new_token: str) -> None:
        """Retire the old capability and create its replacement in one transaction.

        No forwarding capability is retained: an old patient's token must never
        grant access to the next patient's answers.
        """
        old_id = retired.get("guard", {}).get("session_id")
        new_id = fresh.get("guard", {}).get("session_id")
        if (
            not old_id
            or not new_id
            or old_id == new_id
            or old_token == new_token
            or not 32 <= len(old_token) <= 128
            or not 32 <= len(new_token) <= 128
            or retired.get("status") != "closed"
            or fresh.get("status") != "active"
            or fresh.get("flow", {}).get("stage") != "language"
        ):
            raise ValueError("Invalid restart handoff")
        old_hash, new_hash = (
            hmac.new(self._lookup_key, b"resume:" + token.encode(), hashlib.sha256).hexdigest()
            for token in (old_token, new_token)
        )
        old_payload, new_payload = (
            self.cipher.encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            for data in (retired, fresh)
        )
        with self._connect() as connection:
            updated = connection.execute(
                "UPDATE workflows SET payload=? WHERE session_id=? AND token_hash=?",
                (old_payload, old_id, old_hash),
            )
            if updated.rowcount != 1:
                raise ValueError("Restart capability does not own this encounter")
            connection.execute(
                "INSERT INTO workflows VALUES (?, ?, ?)",
                (new_id, new_hash, new_payload),
            )

    def save_completion(self, session_id: str, payload: dict, resume_token: str) -> None:
        """Commit the report and its completed workflow receipt in one SQLite transaction."""
        report = payload.get("flow", {}).get("report") or {}
        if (
            payload.get("guard", {}).get("session_id") != session_id
            or not 32 <= len(resume_token) <= 128
            or payload.get("status") != "complete"
            or report.get("completion") != "saved_local"
        ):
            raise ValueError("Invalid completion receipt")
        encrypted = self.cipher.encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        encrypted_report = self.cipher.encrypt(
            json.dumps(report, ensure_ascii=False).encode("utf-8")
        )
        token_hash = hmac.new(
            self._lookup_key, b"resume:" + resume_token.encode(), hashlib.sha256
        ).hexdigest()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO reports VALUES (?, ?) ON CONFLICT(encounter_id) "
                "DO UPDATE SET encrypted_report=excluded.encrypted_report",
                (session_id, encrypted_report),
            )
            connection.execute(
                "INSERT INTO workflows VALUES (?, ?, ?) ON CONFLICT(session_id) "
                "DO UPDATE SET payload=excluded.payload, token_hash=excluded.token_hash",
                (session_id, token_hash, encrypted),
            )

    def load_workflow(self, resume_token: str) -> dict | None:
        if not 32 <= len(resume_token) <= 128:
            return None
        token_hash = hmac.new(
            self._lookup_key, b"resume:" + resume_token.encode(), hashlib.sha256
        ).hexdigest()
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='workflows'"
            ).fetchone()
            if not exists:
                return None
            row = connection.execute(
                "SELECT session_id, payload FROM workflows WHERE token_hash=?", (token_hash,)
            ).fetchone()
        if not row:
            return None
        data = json.loads(self.cipher.decrypt(row[1]))
        if data.get("status") == "closed":
            return None
        if data.get("status") == "complete":
            flow = data.get("flow", {})
            if (
                flow.get("stage") not in {"report", "emergency"}
                or (flow.get("report") or {}).get("completion") != "saved_local"
            ):
                return None
        return {"session_id": row[0], "data": data}

    def save_report(self, encounter_id: str, report: dict) -> None:
        encrypted = self.cipher.encrypt(json.dumps(report, ensure_ascii=False).encode("utf-8"))
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
