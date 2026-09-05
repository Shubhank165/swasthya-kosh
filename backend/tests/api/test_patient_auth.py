"""Phone sign-in for the patient app — 2/3 §7.1, §12.

These two routes are the only writable surface in the system reachable with no
credential at all, because acquiring a credential is what they are for. That
makes them the ones worth testing hardest, and most of what is asserted here is
about what the endpoints *refuse* to do: reveal whether a number is known,
accept an unlimited number of guesses, or hand back anything that reverses to a
phone number.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Settings
from app.core.errors import ConfigurationError, ValidationError
from app.services.patient_auth import normalise_phone, phone_ref

PHONE = "9876543210"


@pytest.fixture(autouse=True)
def _stable_ids(app_client: Any) -> None:
    """One id factory for the whole client, not one per request.

    `app_client` overrides `get_ids` with the `SequentialIdFactory` *class*, so
    every request builds a fresh counter and every request generates
    `otp_000001`. Fine when a test makes one write; these tests make several,
    and the second one collides on the primary key. Production ids do not
    collide — this is a harness artefact, fixed in the harness.
    """
    from app.api import deps
    from tests.conftest import SequentialIdFactory

    shared = SequentialIdFactory()
    app_client.app.dependency_overrides[deps.get_ids] = lambda: shared


def _request(client: Any, phone: str = PHONE) -> dict[str, Any]:
    response = client.post("/api/v1/auth/otp/request", json={"phone": phone})
    assert response.status_code == 201, response.text
    return dict(response.json())


def _sign_in(client: Any, phone: str = PHONE) -> str:
    challenge = _request(client, phone)
    response = client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge["challenge_id"], "code": challenge["code"]},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["token"])


class TestTheNumberIsNeverStored:
    def test_the_reference_is_not_a_plain_digest(self) -> None:
        """The whole privacy argument for the exempt tables rests on this.

        An Indian mobile number is ten digits — under a billion candidates. A
        plain SHA-256 of one is reversed by exhaustive search in seconds, so a
        bare digest would be the phone book with extra steps.
        """
        import hashlib

        peppered = phone_ref(PHONE, pepper="a-pepper")
        plain = hashlib.sha256(PHONE.encode()).hexdigest()
        assert peppered != plain

    def test_a_different_pepper_gives_a_different_reference(self) -> None:
        assert phone_ref(PHONE, pepper="one") != phone_ref(PHONE, pepper="two")

    def test_no_pepper_refuses_rather_than_falling_back(self) -> None:
        """Fails closed.

        A fallback to an unpeppered digest is the failure mode where everything
        works, nothing errors, and the privacy property is silently absent.
        """
        with pytest.raises(ConfigurationError, match="PATIENT_REF_PEPPER"):
            phone_ref(PHONE, pepper=None)

    @pytest.mark.parametrize(
        "written", ["9876543210", "+919876543210", "09876543210", "+91 98765 43210"]
    )
    def test_one_number_written_four_ways_is_one_patient(self, written: str) -> None:
        """Otherwise the same person has four accounts and four histories."""
        assert normalise_phone(written) == PHONE

    @pytest.mark.parametrize("bad", ["12345", "98765432101234", "not-a-number", ""])
    def test_a_number_that_is_not_a_number_is_refused(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            normalise_phone(bad)


class TestRequestingACode:
    def test_a_challenge_is_issued(self, app_client: Any) -> None:
        body = _request(app_client)
        assert body["challenge_id"]
        assert body["delivery"] == "mock"

    def test_the_response_never_echoes_the_number(self, app_client: Any) -> None:
        """An endpoint that confirms "we texted 98765xxxxx" confirms the number
        is real to whoever typed it, which may not be its owner."""
        body = _request(app_client)
        assert PHONE not in str(body)

    def test_an_unknown_number_looks_identical_to_a_known_one(
        self, app_client: Any
    ) -> None:
        """No membership oracle.

        Patients of an AYUSH hospital are an identifiable group; "does this
        number have an account" must not be answerable by a stranger.
        """
        first = _sign_in(app_client)
        assert first
        known = _request(app_client, PHONE)
        unknown = _request(app_client, "9000000001")
        assert known.keys() == unknown.keys()

    def test_requesting_again_invalidates_the_previous_code(
        self, app_client: Any
    ) -> None:
        """Two live codes for one phone doubles the guessing surface."""
        first = _request(app_client)
        _request(app_client)
        response = app_client.post(
            "/api/v1/auth/otp/verify",
            json={"challenge_id": first["challenge_id"], "code": first["code"]},
        )
        assert response.status_code == 401

    def test_a_number_cannot_be_used_as_an_sms_cannon(self, app_client: Any) -> None:
        """Rate limited per number per hour.

        Unlimited, this endpoint is free SMS anyone can aim at a stranger's
        phone, billed to the hospital.
        """
        codes = [
            app_client.post("/api/v1/auth/otp/request", json={"phone": "9000000002"})
            for _ in range(7)
        ]
        assert any(r.status_code == 422 for r in codes), [r.status_code for r in codes]


class TestVerifying:
    def test_the_right_code_returns_a_session(self, app_client: Any) -> None:
        token = _sign_in(app_client)
        assert len(token) > 20

    def test_the_wrong_code_is_refused(self, app_client: Any) -> None:
        challenge = _request(app_client)
        response = app_client.post(
            "/api/v1/auth/otp/verify",
            json={"challenge_id": challenge["challenge_id"], "code": "000000"},
        )
        assert response.status_code == 401

    def test_every_failure_reads_the_same(self, app_client: Any) -> None:
        """Wrong code, unknown challenge and spent challenge are one message.

        Distinguishing them tells an attacker which half of the pair they got
        right, and turns the endpoint into an oracle.
        """
        challenge = _request(app_client)
        wrong = app_client.post(
            "/api/v1/auth/otp/verify",
            json={"challenge_id": challenge["challenge_id"], "code": "000000"},
        )
        missing = app_client.post(
            "/api/v1/auth/otp/verify",
            json={"challenge_id": "otp_does_not_exist", "code": "000000"},
        )
        assert wrong.json()["message"] == missing.json()["message"]
        assert wrong.json()["code"] == missing.json()["code"]

    def test_a_code_cannot_be_replayed(self, app_client: Any) -> None:
        challenge = _request(app_client)
        first = app_client.post(
            "/api/v1/auth/otp/verify",
            json={"challenge_id": challenge["challenge_id"], "code": challenge["code"]},
        )
        assert first.status_code == 200
        second = app_client.post(
            "/api/v1/auth/otp/verify",
            json={"challenge_id": challenge["challenge_id"], "code": challenge["code"]},
        )
        assert second.status_code == 401

    def test_guessing_is_bounded(self, app_client: Any) -> None:
        """A six-digit code with unlimited attempts is a four-hour brute force.

        After the cap the challenge is burned, so even the correct code no
        longer works — the attacker has to request a new one, which is rate
        limited, which is the point.
        """
        challenge = _request(app_client)
        for _ in range(6):
            app_client.post(
                "/api/v1/auth/otp/verify",
                json={"challenge_id": challenge["challenge_id"], "code": "000000"},
            )
        correct = app_client.post(
            "/api/v1/auth/otp/verify",
            json={"challenge_id": challenge["challenge_id"], "code": challenge["code"]},
        )
        assert correct.status_code == 401


class TestTheCodeIsNotRevealedInProduction:
    async def test_the_mock_sender_stays_silent_in_production(
        self, session: Any, settings: Settings, clock: Any, ids: Any
    ) -> None:
        """The one path that could leak a live OTP through the API.

        The mock sender returning the code is what makes an offline demo
        possible. It must not survive a deployment where somebody left
        `OTP_PROVIDER=mock` set — so the service gates on the environment as
        well as on the sender.
        """
        from app.adapters.otp.senders import MockOTPSender
        from app.services.patient_auth import PatientAuthService

        production = settings.model_copy(update={"environment": "production"})
        service = PatientAuthService(
            session,
            settings=production,
            sender=MockOTPSender(),
            clock=clock,
            ids=ids,
        )
        challenge = await service.request_code(PHONE)
        assert challenge.code is None


class TestWhatASessionCanReach:
    def test_a_patient_reads_their_own_history(self, app_client: Any) -> None:
        from tests.conftest import HOSPITAL_ID

        token = _sign_in(app_client)
        response = app_client.get(
            "/api/v1/patients/me/history",
            headers={"Authorization": f"Bearer {token}", "X-Hospital-Id": HOSPITAL_ID},
        )
        assert response.status_code == 200
        assert response.json()["intakes"] == []

    def test_a_patient_links_an_abha_address(self, app_client: Any) -> None:
        """2/3 §7.2 — optional, and the answer says it came from a mock."""
        from tests.conftest import HOSPITAL_ID

        token = _sign_in(app_client)
        response = app_client.post(
            "/api/v1/patients/me/abha",
            json={"abha_address": "someone@sbx"},
            headers={"Authorization": f"Bearer {token}", "X-Hospital-Id": HOSPITAL_ID},
        )
        assert response.status_code == 200
        body = response.json()
        # Passed through verbatim so nobody demos a mocked government
        # integration as a live one.
        assert body["source"] == "mock"

    def test_a_failed_abha_lookup_does_not_block_anything(
        self, app_client: Any
    ) -> None:
        """The entire app works with a phone number alone (§7.3).

        A lookup that finds nothing answers `verified: false` and the intake
        proceeds. Turning a patient away because a government API was down is
        not a trade this project makes anywhere.
        """
        from tests.conftest import HOSPITAL_ID

        token = _sign_in(app_client)
        headers = {"Authorization": f"Bearer {token}", "X-Hospital-Id": HOSPITAL_ID}
        response = app_client.post(
            "/api/v1/patients/me/abha",
            json={"abha_address": ""},
            headers=headers,
        )
        assert response.status_code in {200, 422}
        # Whatever the answer, history still works.
        assert app_client.get("/api/v1/patients/me/history", headers=headers).status_code == 200

    def test_a_patient_cannot_read_the_worklist(self, app_client: Any) -> None:
        from tests.conftest import HOSPITAL_ID

        token = _sign_in(app_client)
        response = app_client.get(
            "/api/v1/worklist",
            headers={"Authorization": f"Bearer {token}", "X-Hospital-Id": HOSPITAL_ID},
        )
        assert response.status_code == 403

    def test_a_patient_cannot_read_another_patients_history(
        self, app_client: Any
    ) -> None:
        """`/{ref}/history` is staff-only, so the obvious way to ask for
        somebody else's records is refused by role before identity is even
        considered."""
        from tests.conftest import HOSPITAL_ID

        token = _sign_in(app_client)
        response = app_client.get(
            "/api/v1/patients/UHID-100241/history",
            headers={"Authorization": f"Bearer {token}", "X-Hospital-Id": HOSPITAL_ID},
        )
        assert response.status_code == 403

    def test_me_history_is_not_reachable_by_staff(self, app_client: Any) -> None:
        """"My history" has no meaning for a staff account, and answering it
        would mean inventing one."""
        from tests.conftest import STAFF_HEADERS

        response = app_client.get("/api/v1/patients/me/history", headers=STAFF_HEADERS)
        assert response.status_code == 403

    def test_a_revoked_session_stops_working(self, app_client: Any) -> None:
        from tests.conftest import HOSPITAL_ID

        token = _sign_in(app_client)
        headers = {"Authorization": f"Bearer {token}", "X-Hospital-Id": HOSPITAL_ID}
        assert app_client.get("/api/v1/patients/me/history", headers=headers).status_code == 200

        assert app_client.post(
            "/api/v1/auth/otp/sign-out", headers=headers
        ).status_code == 204
        after = app_client.get("/api/v1/patients/me/history", headers=headers)
        assert after.status_code == 401

    def test_signing_out_an_invalid_token_still_succeeds(self, app_client: Any) -> None:
        """It must not report whether the token was valid."""
        assert app_client.post(
            "/api/v1/auth/otp/sign-out",
            headers={"Authorization": "Bearer nonsense"},
        ).status_code == 204

    def test_a_session_without_a_hospital_is_refused(self, app_client: Any) -> None:
        """The credential says who; the header says where.

        A patient may submit to any hospital they choose, so the hospital cannot
        come from the token — but a request that names none has no tenant to
        scope its query to, and guessing one would be the tenancy bug the whole
        guard exists to prevent.
        """
        token = _sign_in(app_client)
        response = app_client.get(
            "/api/v1/patients/me/history",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    def test_an_unrecognised_bearer_token_is_refused(self, app_client: Any) -> None:
        from tests.conftest import HOSPITAL_ID

        response = app_client.get(
            "/api/v1/patients/me/history",
            headers={
                "Authorization": "Bearer not-a-real-token",
                "X-Hospital-Id": HOSPITAL_ID,
            },
        )
        assert response.status_code == 401
