from fastapi.testclient import TestClient
from test_staff_auth import setup as _setup  # noqa: F401

from medikiosk.app import create_app


def test_full_report_and_authenticated_correction_survive_restart(setup):
    settings, store = setup
    store.save_report(
        "synthetic", {"completion": "saved_local", "clinical": {"complaint": "synthetic complaint"}}
    )

    def login(client):
        result = client.post(
            "/api/staff/login",
            headers={"Origin": "https://testserver"},
            json={"username": "test-clinician", "password": "synthetic-only-password"},
        )
        assert result.status_code == 200
        return {"Origin": "https://testserver", "X-CSRF-Token": result.json()["csrf_token"]}

    with TestClient(create_app(settings), base_url="https://testserver") as client:
        headers = login(client)
        response = client.get("/api/encounters/synthetic")
        assert response.json()["report"]["clinical"]["complaint"] == "synthetic complaint"
        response = client.post(
            "/api/encounters/synthetic/correct",
            headers=headers,
            json={"key": "age_years", "value": 42, "by": "spoofed identity"},
        )
        assert response.json()["ok"]
    with TestClient(create_app(settings), base_url="https://testserver") as restarted:
        assert restarted.get("/api/encounters/synthetic").status_code == 401
        login(restarted)
        report = restarted.get("/api/encounters/synthetic").json()["report"]
        assert report["provenance"]["entries"][0]["value"] == 42
        assert report["provenance"]["entries"][0]["corrected_by"] == "test-clinician"
    raw = settings.session_store_path.read_bytes()
    assert b"synthetic complaint" not in raw
    assert b"test-clinician" not in raw
    assert b"spoofed identity" not in raw
