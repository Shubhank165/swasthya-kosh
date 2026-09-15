"""ABHA identity at the kiosk, without the ABDM gateway.

Real ABHA lookup is a network call to the ABDM gateway, which a kiosk sitting in a camp with no
uplink cannot make. What it *can* do offline is read the ABHA number off the patient's own card
and use it as the key to records this kiosk itself wrote on previous visits. A returning patient
gets their history back; a new one gets enrolled. Nothing is invented and nothing is claimed to
have come from ABDM.

ABHA numbers are 14 digits, usually printed as 12-3456-7890-1234, and ABHA addresses look like
`name@abdm`. The QR on the card carries JSON with a "hidn"/"healthIdNumber" field. Both routes end
at the same normalised 14-digit key.

The number itself is identifying, so it is never stored in the clear: rows are keyed by a salted
hash and the visit body is Fernet-encrypted exactly like EncryptedSessionStore does. A stolen
database file yields neither the ABHA numbers nor the complaints.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet

ABHA_DIGITS = re.compile(r"\d{14}")


def normalise(raw: str) -> str | None:
    """A bare 14-digit ABHA number from whatever the patient typed or the card encoded."""

    digits = re.sub(r"\D", "", raw or "")
    return digits if len(digits) == 14 else None


def from_qr_payload(payload: str) -> str | None:
    """Pull the ABHA number out of a scanned card. Handles the JSON form and a bare number."""

    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        match = ABHA_DIGITS.search(re.sub(r"\D", "", payload or ""))
        return match.group(0) if match else None
    for key in ("hidn", "healthIdNumber", "abhaNumber", "health_id_number"):
        value = data.get(key) if isinstance(data, dict) else None
        if value and (number := normalise(str(value))):
            return number
    return None


def scan_qr(image) -> str | None:
    """Decode an ABHA QR from a PIL image or numpy array. Returns None when nothing is readable."""

    import cv2
    import numpy

    frame = numpy.array(image)
    if frame.ndim == 3 and frame.shape[2] == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    try:
        payload, points, _ = cv2.QRCodeDetector().detectAndDecode(frame)
    except cv2.error:
        return None
    if not payload or points is None:
        return None
    return from_qr_payload(payload)


class VisitRecords:
    """Past visits this kiosk recorded, keyed by a salted hash of the ABHA number."""

    def __init__(self, path: Path, encryption_key: str) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cipher = Fernet(encryption_key.encode("ascii"))
        # The Fernet key doubles as the HMAC salt: same secret, same blast radius, one thing to
        # rotate. Without a salt an attacker could hash all 10^14 ABHA numbers and match the keys.
        self._salt = encryption_key.encode("ascii")
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS visits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    abha_key TEXT NOT NULL,
                    encrypted_visit BLOB NOT NULL,
                    recorded_at TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS visits_by_abha ON visits(abha_key)")

    def _key(self, abha_number: str) -> str:
        return hmac.new(self._salt, abha_number.encode("ascii"), hashlib.sha256).hexdigest()

    def save(self, abha_number: str, visit: dict) -> None:
        payload = dict(visit)
        payload.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
        encrypted = self.cipher.encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO visits(abha_key, encrypted_visit, recorded_at) VALUES (?, ?, ?)",
                (self._key(abha_number), encrypted, payload["recorded_at"]),
            )

    def history(self, abha_number: str, limit: int = 5) -> list[dict]:
        """Most recent visits first. Unreadable rows are skipped, never raised at a patient."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT encrypted_visit FROM visits
                WHERE abha_key = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (self._key(abha_number), limit),
            ).fetchall()
        visits = []
        for (blob,) in rows:
            try:
                visits.append(json.loads(self.cipher.decrypt(blob)))
            except Exception:
                continue  # a row written under a rotated key must not break a live intake
        return visits

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)
