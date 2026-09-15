import sqlite3

import pytest
from cryptography.fernet import Fernet

from medikiosk.kiosk.protocol import SessionGuard
from medikiosk.models import PatientState
from medikiosk.storage import EncryptedSessionStore


def test_sqlite_payload_is_encrypted(tmp_path) -> None:
    database = tmp_path / "sessions.db"
    store = EncryptedSessionStore(database, Fernet.generate_key().decode("ascii"))
    state = PatientState(complaint="private test complaint")
    store.save("session-1", state)

    assert b"private test complaint" not in database.read_bytes()
    assert store.load("session-1") == state


@pytest.mark.parametrize("collision", ["session_id", "capability", "wrong_owner"])
def test_restart_never_overwrites_another_workflow(tmp_path, collision):
    store = EncryptedSessionStore(tmp_path / "sessions.db", Fernet.generate_key().decode())
    old, fresh, other = SessionGuard(), SessionGuard(), SessionGuard()
    initial = {"guard": old.snapshot(), "status": "active", "flow": {"stage": "interview"}}
    unrelated = {"guard": other.snapshot(), "status": "active", "flow": {"stage": "interview"}}
    store.save_workflow(old.session_id, initial, old.token)
    store.save_workflow(other.session_id, unrelated, other.token)
    if collision == "session_id":
        fresh.session_id = other.session_id
    elif collision == "capability":
        fresh.token = other.token
    replacement = {"guard": fresh.snapshot(), "status": "active", "flow": {"stage": "language"}}
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        store.restart_workflow(
            {**initial, "status": "closed"},
            other.token if collision == "wrong_owner" else old.token,
            replacement,
            fresh.token,
        )
    assert store.load_workflow(old.token)["data"] == initial
    assert store.load_workflow(other.token)["data"] == unrelated
