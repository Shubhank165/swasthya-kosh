"""The four endpoints the doctor dashboard needs — 3/3 §10.

Per-fact verification, the alerts list, the correction rate, and the worklist's
state filter. Each is asserted against the property that made it worth building
rather than merely against its status code:

- amending writes a **revision** and leaves the original in place, because the
  correction rate is computed from the pair;
- rejecting produces `unresolved`, **never** an answered `no`;
- acknowledging and escalating stay two separate acts;
- the state filter cannot hide an unacknowledged alert.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from tests.conftest import (
    ADMIN_HEADERS,
    KIOSK_HEADERS,
    PHYSICIAN_HEADERS,
    STAFF_HEADERS,
)


def _ingest(client: Any, payload: dict[str, Any]) -> str:
    response = client.post(
        "/api/v1/intakes/ingest", headers=KIOSK_HEADERS, json=payload
    )
    assert response.status_code == 200, response.text
    return str(response.json()["intake_id"])


def _fact(client: Any, intake_id: str, field_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/intakes/{intake_id}", headers=STAFF_HEADERS)
    assert response.status_code == 200, response.text
    facts = [f for f in response.json()["facts"] if f["field_id"] == field_id]
    assert facts, f"no live fact for {field_id!r}"
    return facts[0]


@pytest.fixture
def intake_id(app_client: Any, kiosk_payload: dict[str, Any]) -> str:
    return _ingest(app_client, kiosk_payload)


class TestVerifyingOneFact:
    """§6: accept, amend or reject, one line at a time."""

    def test_accepting_marks_the_fact_verified(
        self, app_client: Any, intake_id: str
    ) -> None:
        fact = _fact(app_client, intake_id, "chief_complaint")
        assert fact["physician_verified"] is False

        response = app_client.post(
            f"/api/v1/intakes/{intake_id}/facts/{fact['fact_id']}/verify",
            headers=PHYSICIAN_HEADERS,
            json={"action": "verified"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["physician_verified"] is True
        assert body["physician_action"] == "verified"
        assert body["rendered"] == fact["rendered"]
        # A new revision, not the same row edited.
        assert body["fact_id"] != fact["fact_id"]

    def test_amending_replaces_the_value_and_keeps_the_original(
        self, app_client: Any, intake_id: str
    ) -> None:
        """The original survives, and that is the point.

        The correction rate is the proportion of facts a physician amends. A
        store that overwrote the extracted value could not produce it, and the
        report could no longer show what the pipeline actually heard.
        """
        fact = _fact(app_client, intake_id, "duration")
        response = app_client.post(
            f"/api/v1/intakes/{intake_id}/facts/{fact['fact_id']}/verify",
            headers=PHYSICIAN_HEADERS,
            json={
                "action": "amended",
                "value": {"kind": "duration", "magnitude": 5, "unit": "day"},
                "reason": "patient corrected on arrival",
            },
        )
        assert response.status_code == 200, response.text
        amended = response.json()
        assert amended["rendered"] == "5 days"
        assert amended["physician_action"] == "amended"
        assert amended["certainty"] == "confirmed"

        # The live view shows the amendment…
        assert _fact(app_client, intake_id, "duration")["rendered"] == "5 days"
        # …and the patient's own words are not the physician's to revise.
        assert amended["original_text"] == fact["original_text"]

    def test_rejecting_produces_unresolved_and_never_a_no(
        self, app_client: Any, intake_id: str
    ) -> None:
        """The distinction the whole record model exists to protect.

        Rejecting a misheard "diabetes" means nobody knows whether the patient
        is diabetic. It does not mean they are not, and writing it as
        `answered: false` would be a clinical claim made by a correction.
        """
        fact = _fact(app_client, intake_id, "known_diabetes")
        assert fact["status"] == "answered"

        response = app_client.post(
            f"/api/v1/intakes/{intake_id}/facts/{fact['fact_id']}/verify",
            headers=PHYSICIAN_HEADERS,
            json={"action": "rejected", "reason": "misheard"},
        )
        assert response.status_code == 200, response.text
        rejected = response.json()
        assert rejected["status"] == "unresolved"
        assert rejected["value"] is None
        assert rejected["rendered"] is None
        assert rejected["physician_verified"] is False
        assert rejected["physician_action"] == "rejected"

    def test_an_unanswered_field_cannot_be_accepted(
        self, app_client: Any, intake_id: str
    ) -> None:
        """A signature on a field nobody answered would establish it."""
        fact = _fact(app_client, intake_id, "severity")
        assert fact["status"] == "unresolved"
        response = app_client.post(
            f"/api/v1/intakes/{intake_id}/facts/{fact['fact_id']}/verify",
            headers=PHYSICIAN_HEADERS,
            json={"action": "verified"},
        )
        assert response.status_code == 422
        assert response.json()["details"]["status"] == "unresolved"

    def test_an_amendment_without_a_value_is_refused(
        self, app_client: Any, intake_id: str
    ) -> None:
        fact = _fact(app_client, intake_id, "duration")
        response = app_client.post(
            f"/api/v1/intakes/{intake_id}/facts/{fact['fact_id']}/verify",
            headers=PHYSICIAN_HEADERS,
            json={"action": "amended"},
        )
        assert response.status_code == 422

    def test_acting_on_a_superseded_revision_is_a_conflict(
        self, app_client: Any, intake_id: str
    ) -> None:
        """Two clinicians with the same report open is a real sequence.

        The second one is told rather than having their edit land on a fact
        nobody is looking at any more.
        """
        fact = _fact(app_client, intake_id, "chief_complaint")
        path = f"/api/v1/intakes/{intake_id}/facts/{fact['fact_id']}/verify"
        assert app_client.post(
            path, headers=PHYSICIAN_HEADERS, json={"action": "verified"}
        ).status_code == 200
        again = app_client.post(
            path, headers=PHYSICIAN_HEADERS, json={"action": "rejected"}
        )
        assert again.status_code == 409

    def test_an_unknown_fact_is_404(self, app_client: Any, intake_id: str) -> None:
        response = app_client.post(
            f"/api/v1/intakes/{intake_id}/facts/no-such-fact/verify",
            headers=PHYSICIAN_HEADERS,
            json={"action": "verified"},
        )
        assert response.status_code == 404


class TestTheCorrectionRate:
    """§6, §B3: the number that replaces the shelved harness's figures."""

    def test_it_is_null_before_anything_is_reviewed(self, app_client: Any) -> None:
        """Not `0.0`. A zero on an empty denominator reads as "never wrong"."""
        response = app_client.get(
            "/api/v1/metrics/correction-rate", headers=ADMIN_HEADERS
        )
        assert response.status_code == 200
        assert response.json()["correction_rate"] is None

    def test_it_counts_corrections_over_facts_reviewed(
        self, app_client: Any, intake_id: str
    ) -> None:
        for field_id, body in (
            ("chief_complaint", {"action": "verified"}),
            ("current_medications", {"action": "verified"}),
            (
                "duration",
                {
                    "action": "amended",
                    "value": {"kind": "duration", "magnitude": 5, "unit": "day"},
                },
            ),
            ("known_diabetes", {"action": "rejected"}),
        ):
            fact = _fact(app_client, intake_id, field_id)
            assert app_client.post(
                f"/api/v1/intakes/{intake_id}/facts/{fact['fact_id']}/verify",
                headers=PHYSICIAN_HEADERS,
                json=body,
            ).status_code == 200, field_id

        body = app_client.get(
            "/api/v1/metrics/correction-rate", headers=ADMIN_HEADERS
        ).json()
        assert body["facts_reviewed"] == 4
        assert body["verified"] == 2
        assert body["amended"] == 1
        assert body["rejected"] == 1
        assert body["correction_rate"] == 0.5
        assert body["intakes_reviewed"] == 1

    def test_a_field_acted_on_twice_counts_once(
        self, app_client: Any, intake_id: str
    ) -> None:
        """Latest action wins.

        Otherwise a physician who confirms a line and then thinks better of it
        looks worse than one who never checked.
        """
        fact = _fact(app_client, intake_id, "duration")
        assert app_client.post(
            f"/api/v1/intakes/{intake_id}/facts/{fact['fact_id']}/verify",
            headers=PHYSICIAN_HEADERS,
            json={"action": "verified"},
        ).status_code == 200

        revised = _fact(app_client, intake_id, "duration")
        assert app_client.post(
            f"/api/v1/intakes/{intake_id}/facts/{revised['fact_id']}/verify",
            headers=PHYSICIAN_HEADERS,
            json={
                "action": "amended",
                "value": {"kind": "duration", "magnitude": 5, "unit": "day"},
            },
        ).status_code == 200

        body = app_client.get(
            "/api/v1/metrics/correction-rate", headers=ADMIN_HEADERS
        ).json()
        assert body["facts_reviewed"] == 1
        assert body["amended"] == 1
        assert body["verified"] == 0
        assert body["correction_rate"] == 1.0


@pytest.fixture
def flagged_payload(kiosk_payload: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(kiosk_payload)
    payload["intake_id"] = "8d1d8b0e-3d6f-4a52-9b1a-2f0a0c0d0e99"
    payload["status"] = "aborted_red_flag"
    payload["red_flags"] = [
        {
            "rule_id": "gi_bleeding_suspected",
            "fired_at_turn": 4,
            "criteria_met": ["haematemesis"],
            "severity": "critical",
            "label": "Urgent clinical review criterion triggered",
        }
    ]
    return payload


class TestTheAlertsList:
    """§4.3: a dedicated view, unacknowledged first."""

    def test_it_lists_a_fired_criterion_without_naming_a_condition(
        self, app_client: Any, flagged_payload: dict[str, Any]
    ) -> None:
        intake_id = _ingest(app_client, flagged_payload)
        response = app_client.get("/api/v1/alerts", headers=STAFF_HEADERS)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["unacknowledged"] == 1

        alert = next(a for a in body["alerts"] if a["intake_id"] == intake_id)
        # The rule's own fixed wording. Every rule in the content carries it,
        # and a label that named a diagnosis would be one this system made.
        assert alert["label"] == "Urgent clinical review criterion triggered"
        assert alert["criteria_met"] == ["haematemesis"]
        assert alert["acknowledged_by"] is None

    def test_acknowledging_records_the_acting_user_and_nothing_else(
        self, app_client: Any, flagged_payload: dict[str, Any]
    ) -> None:
        """Acknowledging is not escalating — §1 rule 2.

        It records that a person looked. It moves nothing up the list, notifies
        nobody, and there is no field in this response that could be mistaken
        for an escalation having happened.
        """
        intake_id = _ingest(app_client, flagged_payload)
        response = app_client.post(
            f"/api/v1/alerts/{intake_id}/acknowledge",
            headers=PHYSICIAN_HEADERS,
            json={"rule_id": "gi_bleeding_suspected", "note": "seen, patient stable"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["acknowledged_by"] == "dr-sharma"

        acknowledged = app_client.get(
            "/api/v1/alerts?acknowledged=true", headers=STAFF_HEADERS
        ).json()
        assert [a["intake_id"] for a in acknowledged["alerts"]] == [intake_id]
        assert acknowledged["unacknowledged"] == 0

        outstanding = app_client.get(
            "/api/v1/alerts?acknowledged=false", headers=STAFF_HEADERS
        ).json()
        assert outstanding["alerts"] == []

    def test_a_patient_token_is_refused(
        self, app_client: Any, flagged_payload: dict[str, Any]
    ) -> None:
        """§11.4. A kiosk holds the narrowest credential in the system and a
        list of who is being urgently reviewed is not in it."""
        _ingest(app_client, flagged_payload)
        assert (
            app_client.get("/api/v1/alerts", headers=KIOSK_HEADERS).status_code == 403
        )


class TestTheWorklistStateFilter:
    def test_filtering_narrows_entries_but_never_the_alert_band(
        self, app_client: Any, kiosk_payload: dict[str, Any], flagged_payload: dict[str, Any]
    ) -> None:
        """§4.1. A dropdown that can hide an unacknowledged red flag is a
        dropdown that has hidden one."""
        _ingest(app_client, kiosk_payload)
        flagged_id = _ingest(app_client, flagged_payload)

        body = app_client.get(
            "/api/v1/worklist?state=needs_review", headers=STAFF_HEADERS
        ).json()
        assert all(e["state"] == "needs_review" for e in body["entries"])
        assert flagged_id not in [e["intake_id"] for e in body["entries"]]
        assert flagged_id in [e["intake_id"] for e in body["pending_alerts"]]
        # `total` still counts the whole window, so a filter that hides rows
        # says so rather than making the department look quiet.
        assert body["total"] > len(body["entries"])

    def test_an_unknown_state_is_rejected(self, app_client: Any) -> None:
        response = app_client.get(
            "/api/v1/worklist?state=urgent", headers=STAFF_HEADERS
        )
        assert response.status_code == 422


class TestVerificationSurvivesARereadOfTheReport:
    """Found by the end-to-end journey, not by a unit test.

    The builder is pure and knows nothing about verification; the verification
    lives on the stored report row. Regenerating the report on every read — which
    is right, because a document that arrived since changes it — dropped the
    sign-off, so a signed record came back looking like a draft.
    """

    def test_a_verified_report_still_says_so_when_read_again(
        self, app_client: Any, intake_id: str
    ) -> None:
        verified = app_client.post(
            f"/api/v1/intakes/{intake_id}/verify",
            headers=PHYSICIAN_HEADERS,
            json={},
        )
        assert verified.status_code == 200, verified.text
        assert verified.json()["physician_verified_by"] == "dr-sharma"

        again = app_client.get(
            f"/api/v1/intakes/{intake_id}/report", headers=STAFF_HEADERS
        )
        assert again.status_code == 200
        assert again.json()["physician_verified_by"] == "dr-sharma"

    def test_an_unverified_report_does_not_claim_a_signature(
        self, app_client: Any, intake_id: str
    ) -> None:
        response = app_client.get(
            f"/api/v1/intakes/{intake_id}/report", headers=STAFF_HEADERS
        )
        assert response.json()["physician_verified_by"] is None
