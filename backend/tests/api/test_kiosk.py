"""`GET /kiosk/whoami` — the provisioning credential check."""

from __future__ import annotations

from typing import Any

from tests.conftest import HOSPITAL_ID, KIOSK_HEADERS, PHYSICIAN_HEADERS, STAFF_HEADERS


class TestWhoAmI:
    def test_a_valid_kiosk_token_gets_its_bound_hospital(
        self, app_client: Any
    ) -> None:
        response = app_client.get("/api/v1/kiosk/whoami", headers=KIOSK_HEADERS)
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "kiosk"
        assert body["hospital_id"] == HOSPITAL_ID
        assert body["user_id"].startswith("kiosk:")

    def test_no_credential_is_401_not_200(self, app_client: Any) -> None:
        """The whole point: unlike `/content/bundle`, a missing token fails
        here, so a device with a broken credential finds out at provisioning
        time rather than on its first upload."""
        assert app_client.get("/api/v1/kiosk/whoami").status_code == 401

    def test_a_garbage_token_is_401(self, app_client: Any) -> None:
        response = app_client.get(
            "/api/v1/kiosk/whoami",
            headers={"Authorization": "Bearer definitely-not-a-real-token"},
        )
        assert response.status_code == 401

    def test_a_staff_header_principal_is_403_not_200(self, app_client: Any) -> None:
        """A non-kiosk principal is authenticated but not what this endpoint is
        for; it must not read as a passing kiosk check."""
        assert (
            app_client.get(
                "/api/v1/kiosk/whoami", headers=STAFF_HEADERS
            ).status_code
            == 403
        )
        assert (
            app_client.get(
                "/api/v1/kiosk/whoami", headers=PHYSICIAN_HEADERS
            ).status_code
            == 403
        )
