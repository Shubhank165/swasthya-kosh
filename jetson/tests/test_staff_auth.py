import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from medikiosk.app import create_app
from medikiosk.config import Settings
from medikiosk.kiosk.staff_auth import StaffAuth, password_hash
from medikiosk.storage import EncryptedSessionStore


@pytest.fixture(name="setup")
def setup(tmp_path):
    users = tmp_path / "synthetic-users.json"
    users.write_text(json.dumps({"test-clinician": password_hash("synthetic-only-password")}))
    users.chmod(0o600)
    settings = Settings(
        _env_file=None,
        deployment_profile="jetson",
        clinical_llm_enabled=False,
        openai_api_key=None,
        sarvam_api_key=None,
        staff_users_path=users,
        session_store_path=tmp_path / "sessions.db",
        session_encryption_key=Fernet.generate_key().decode(),
    )
    store = EncryptedSessionStore(settings.session_store_path, settings.session_encryption_key)
    store.save_report("synthetic", {"completion": "saved_local", "provenance": {"entries": []}})
    return settings, store


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/queue"),
        ("get", "/api/encounters/synthetic"),
        ("post", "/api/encounters/synthetic/correct"),
        ("post", "/api/encounters/synthetic/state"),
    ],
)
def test_patient_cannot_read_or_mutate_staff_records(setup, method, path):
    settings, _ = setup
    with TestClient(create_app(settings)) as client:
        response = getattr(client, method)(path, headers={"X-Kiosk-Token": "not-staff"})
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"


def test_staff_session_requires_origin_csrf_and_server_identity(setup):
    settings, store = setup
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        credentials = {"username": "test-clinician", "password": "synthetic-only-password"}
        assert client.post("/api/staff/login", json=credentials).status_code == 403
        login = client.post(
            "/api/staff/login", json=credentials, headers={"Origin": "https://testserver"}
        )
        assert login.status_code == 200
        assert "HttpOnly" in login.headers["set-cookie"]
        assert "Secure" in login.headers["set-cookie"]
        assert client.get("/api/queue").status_code == 200
        body = {"key": "severity", "value": 4, "by": "spoofed-doctor"}
        assert client.post("/api/encounters/synthetic/correct", json=body).status_code == 403
        headers = {"Origin": "https://testserver", "X-CSRF-Token": login.json()["csrf_token"]}
        assert (
            client.post("/api/encounters/synthetic/correct", json=body, headers=headers).status_code
            == 200
        )
        report = store.load_report("synthetic")
        assert report["provenance"]["entries"][0]["corrected_by"] == "test-clinician"
        assert client.post("/api/staff/logout", headers=headers).status_code == 200
        assert client.get("/api/queue").status_code == 401


def test_production_demo_bypass_is_disabled(setup):
    settings, _ = setup
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/demo-turn", json={"transcript": "synthetic"}).status_code == 404


@pytest.mark.parametrize(
    "body,status",
    [
        (b" " * 8193, 413),
        (b'"not a credentials object"', 400),
        (b"[]", 400),
        (b"null", 400),
        (b'{"username": null, "password": 123}', 400),
        (b'{"username": "missing-password"}', 400),
        (b'\xff{"username":"invalid-encoding"}', 400),
        (b'{"username":"\\ud800","password":"synthetic-only-password"}', 400),
        (b'{"username":"test-clinician","password":"\\ud800"}', 400),
    ],
)
def test_invalid_login_body_is_bounded_and_does_not_echo_input(setup, body, status):
    settings, _ = setup
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = client.post(
            "/api/staff/login", content=body, headers={"Origin": "https://testserver"}
        )
        assert response.status_code == status
        assert response.json()["detail"] in {
            "Invalid staff sign-in",
            "Staff sign-in is too large",
        }
        assert "set-cookie" not in response.headers


def test_chunked_login_body_is_bounded_before_password_check(setup, monkeypatch):
    settings, _ = setup
    monkeypatch.setattr(
        "medikiosk.kiosk.staff_auth.verify_password",
        lambda *args: pytest.fail("Oversized input reached password checking"),
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = client.post(
            "/api/staff/login",
            content=iter([b" " * 4096] * 3),
            headers={"Origin": "https://testserver"},
        )
        assert response.status_code == 413


def test_parallel_logins_reserve_throttle_before_password_check(setup, monkeypatch):
    settings, _ = setup
    auth = StaffAuth(settings.staff_users_path)
    barrier = threading.Barrier(10)
    verified = []

    def verify(password, encoded):
        verified.append(password)
        barrier.wait(timeout=3)
        return False

    monkeypatch.setattr("medikiosk.kiosk.staff_auth.verify_password", verify)

    def attempt(_):
        request = Request(
            {
                "type": "http",
                "scheme": "https",
                "method": "POST",
                "path": "/api/staff/login",
                "query_string": b"",
                "headers": [(b"host", b"testserver"), (b"origin", b"https://testserver")],
            }
        )
        try:
            auth.login(request, "test-clinician", "synthetic-wrong-password")
        except HTTPException as exc:
            return exc.status_code
        pytest.fail("Wrong password accepted")

    with ThreadPoolExecutor(max_workers=20) as pool:
        statuses = list(pool.map(attempt, range(20)))
    assert statuses.count(401) == 10
    assert statuses.count(429) == 10
    assert len(verified) == 10
    assert len(auth.attempts) == 10
    assert not auth.sessions


def test_plain_http_staff_login_is_blocked_by_default(setup):
    settings, _ = setup
    with TestClient(create_app(settings)) as client:
        assert (
            client.post(
                "/api/staff/login",
                headers={"Origin": "http://testserver"},
                json={"username": "test-clinician", "password": "synthetic-only-password"},
            ).status_code
            == 403
        )
