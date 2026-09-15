from cryptography.fernet import Fernet

from medikiosk.models import PatientState
from medikiosk.storage import EncryptedSessionStore


def test_sqlite_payload_is_encrypted(tmp_path) -> None:
    database = tmp_path / "sessions.db"
    store = EncryptedSessionStore(database, Fernet.generate_key().decode("ascii"))
    state = PatientState(complaint="private test complaint")
    store.save("session-1", state)

    assert b"private test complaint" not in database.read_bytes()
    assert store.load("session-1") == state
