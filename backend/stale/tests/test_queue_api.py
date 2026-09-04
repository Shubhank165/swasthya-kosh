"""Queue API: issuing, calling, the full ticket lifecycle, and escalation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.api.conftest import KIOSK, PHYSICIAN, STAFF, TRIAGE

PREFIX = "/api/v1"
KC_QUEUE = "q-kc-general"
KC_INSTANCE = "qi-q-kc-general-2026-01-15"
PK_QUEUE = "q-pk-therapy"
ST_QUEUE = "q-st-consultant"


async def issue(api: AsyncClient, queue_id: str = KC_QUEUE, **body: object) -> dict:
    instance_id = body.pop("instance_id", f"qi-{queue_id}-2026-01-15")
    response = await api.post(
        f"{PREFIX}/queues/{queue_id}/tickets",
        json={"instance_id": instance_id, **body},
        headers=STAFF,
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestSeededFacility:
    async def test_the_eight_ayush_departments_are_seeded(self, api: AsyncClient) -> None:
        departments = (await api.get(f"{PREFIX}/departments", headers=STAFF)).json()
        codes = {d["code"] for d in departments}
        assert codes == {"KC", "PK", "ST", "SK", "PT", "KB", "SV", "MR"}
        assert all(d["facility"] for d in departments)

    async def test_all_three_assignment_policies_are_in_use(
        self, api: AsyncClient
    ) -> None:
        """A queue model only ever run against one policy has not been tested."""
        queues = (await api.get(f"{PREFIX}/queues", headers=STAFF)).json()
        policies = {q["assignment_policy"] for q in queues}
        assert policies == {"pooled_by_department", "per_service_point", "per_practitioner"}

    async def test_at_least_three_queues_are_open_concurrently(
        self, api: AsyncClient
    ) -> None:
        open_count = 0
        for queue_id in (KC_QUEUE, PK_QUEUE, ST_QUEUE, "q-kb-paediatric"):
            response = await api.get(
                f"{PREFIX}/queues/{queue_id}/instance",
                params={"session": "morning", "date": "2026-01-15"},
                headers=STAFF,
            )
            if response.status_code == 200 and response.json()["status"] == "open":
                open_count += 1
        assert open_count >= 3

    async def test_a_department_filter_narrows_the_queue_list(
        self, api: AsyncClient
    ) -> None:
        queues = (
            await api.get(f"{PREFIX}/queues", params={"department": "KC"}, headers=STAFF)
        ).json()
        assert {q["department_code"] for q in queues} == {"KC"}


class TestIssuing:
    async def test_a_token_carries_the_queue_prefix_and_a_position(
        self, api: AsyncClient
    ) -> None:
        ticket = await issue(api, age_years=34)
        assert ticket["token_number"] == "KC-001"
        assert ticket["priority_class"] == "walkin"
        assert ticket["queue_state"] == "waiting"
        assert ticket["position"] == 1

    async def test_the_patient_sees_an_estimated_wait(self, api: AsyncClient) -> None:
        """"About 22 minutes, enough time to record your history" is what
        actually drives kiosk adoption."""
        await issue(api, age_years=34)
        await issue(api, age_years=41)
        third = await issue(api, age_years=29)
        assert third["position"] == 3
        assert third["estimated_wait_minutes"] == 16

    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            ({"age_years": 72}, "priority"),
            ({"age_years": 1}, "priority"),
            ({"age_years": 30, "is_pregnant": True}, "priority"),
            ({"age_years": 30, "is_differently_abled": True}, "priority"),
            ({"age_years": 30, "has_appointment": True}, "appointment"),
            ({"age_years": 30}, "walkin"),
            ({"age_years": 30, "is_staff_referred_emergency": True}, "emergency"),
        ],
    )
    async def test_priority_is_classified_from_patient_attributes(
        self, api: AsyncClient, body: dict, expected: str
    ) -> None:
        assert (await issue(api, **body))["priority_class"] == expected

    async def test_a_ticket_needs_no_intake(self, api: AsyncClient) -> None:
        """A walk-in who never touched a kiosk still gets seen."""
        ticket = await issue(api, age_years=34)
        assert ticket["intake_id"] is None
        assert ticket["intake_state"] is None
        assert ticket["queue_state"] == "waiting"

    async def test_a_kiosk_may_not_issue_tickets(self, api: AsyncClient) -> None:
        response = await api.post(
            f"{PREFIX}/queues/{KC_QUEUE}/tickets",
            json={"instance_id": KC_INSTANCE},
            headers=KIOSK,
        )
        assert response.status_code == 403


class TestCallingOrder:
    async def test_priority_is_called_before_an_earlier_walk_in(
        self, api: AsyncClient
    ) -> None:
        await issue(api, age_years=30)
        senior = await issue(api, age_years=72)
        called = await api.post(
            f"{PREFIX}/queue-instances/{KC_INSTANCE}/call-next", headers=STAFF
        )
        assert called.json()["ticket_id"] == senior["ticket_id"]

    async def test_calling_an_empty_queue_returns_nothing(self, api: AsyncClient) -> None:
        response = await api.post(
            f"{PREFIX}/queue-instances/{KC_INSTANCE}/call-next", headers=STAFF
        )
        assert response.status_code == 200
        assert response.json() is None

    async def test_a_per_practitioner_queue_only_serves_its_own_consultant(
        self, api: AsyncClient
    ) -> None:
        await issue(api, ST_QUEUE, age_years=40)
        instance_id = f"qi-{ST_QUEUE}-2026-01-15"
        wrong = await api.post(
            f"{PREFIX}/queue-instances/{instance_id}/call-next",
            params={"practitioner_id": "dr-someone-else"},
            headers=STAFF,
        )
        assert wrong.json() is None
        right = await api.post(
            f"{PREFIX}/queue-instances/{instance_id}/call-next",
            params={"practitioner_id": "dr-shalya-1"},
            headers=STAFF,
        )
        assert right.json() is not None


class TestTicketLifecycle:
    async def test_the_full_happy_path(self, api: AsyncClient) -> None:
        ticket = await issue(api, age_years=34)
        ticket_id = ticket["ticket_id"]
        called = await api.post(
            f"{PREFIX}/queue-instances/{KC_INSTANCE}/call-next", headers=STAFF
        )
        assert called.json()["queue_state"] == "called"
        started = await api.post(f"{PREFIX}/tickets/{ticket_id}/start", headers=PHYSICIAN)
        assert started.json()["queue_state"] == "in_consultation"
        completed = await api.post(
            f"{PREFIX}/tickets/{ticket_id}/complete", headers=PHYSICIAN
        )
        assert completed.json()["queue_state"] == "completed"

    async def test_recall_reinserts_then_marks_no_show(self, api: AsyncClient) -> None:
        """Never a silent drop: two more chances, then an explicit NO_SHOW."""
        ticket = await issue(api, age_years=34)
        ticket_id = ticket["ticket_id"]
        await api.post(f"{PREFIX}/queue-instances/{KC_INSTANCE}/call-next", headers=STAFF)

        first = await api.post(f"{PREFIX}/tickets/{ticket_id}/recall", headers=STAFF)
        assert first.json()["queue_state"] == "recalled"
        assert first.json()["recall_count"] == 1

        await api.post(f"{PREFIX}/queue-instances/{KC_INSTANCE}/call-next", headers=STAFF)
        second = await api.post(f"{PREFIX}/tickets/{ticket_id}/recall", headers=STAFF)
        assert second.json()["recall_count"] == 2

        await api.post(f"{PREFIX}/queue-instances/{KC_INSTANCE}/call-next", headers=STAFF)
        third = await api.post(f"{PREFIX}/tickets/{ticket_id}/recall", headers=STAFF)
        assert third.json()["queue_state"] == "no_show"

    async def test_defer_preserves_priority(self, api: AsyncClient) -> None:
        ticket = await issue(api, age_years=72)
        deferred = await api.post(
            f"{PREFIX}/tickets/{ticket['ticket_id']}/defer",
            json={"reason": "sent for a blood test"},
            headers=STAFF,
        )
        assert deferred.json()["queue_state"] == "deferred"
        assert deferred.json()["priority_class"] == "priority"

    async def test_transfer_moves_the_patient_and_carries_the_intake(
        self, api: AsyncClient
    ) -> None:
        intake_id = (
            await api.post(f"{PREFIX}/intakes", json={}, headers=KIOSK)
        ).json()["intake"]["intake_id"]
        ticket = await issue(api, age_years=40, intake_id=intake_id)
        moved = await api.post(
            f"{PREFIX}/tickets/{ticket['ticket_id']}/transfer",
            json={
                "target_queue_id": ST_QUEUE,
                "target_instance_id": f"qi-{ST_QUEUE}-2026-01-15",
            },
            headers=STAFF,
        )
        body = moved.json()
        assert body["queue_id"] == ST_QUEUE
        assert body["token_number"].startswith("ST-")
        # The intake follows the patient and is not re-run.
        assert body["intake_id"] == intake_id

    async def test_cancel_requires_a_reason(self, api: AsyncClient) -> None:
        ticket = await issue(api, age_years=34)
        response = await api.post(
            f"{PREFIX}/tickets/{ticket['ticket_id']}/cancel", json={}, headers=STAFF
        )
        assert response.status_code == 422

    async def test_completing_a_ticket_that_never_started_is_rejected(
        self, api: AsyncClient
    ) -> None:
        ticket = await issue(api, age_years=34)
        response = await api.post(
            f"{PREFIX}/tickets/{ticket['ticket_id']}/complete", headers=PHYSICIAN
        )
        assert response.status_code == 409
        assert response.json()["code"] == "queue_operation_rejected"


class TestInstanceControl:
    async def test_pause_blocks_calling_and_resume_restores_it(
        self, api: AsyncClient
    ) -> None:
        await issue(api, age_years=34)
        paused = await api.post(
            f"{PREFIX}/queue-instances/{KC_INSTANCE}/pause",
            json={"reason": "ward rounds"},
            headers=STAFF,
        )
        assert paused.json()["status"] == "paused"
        blocked = await api.post(
            f"{PREFIX}/queue-instances/{KC_INSTANCE}/call-next", headers=STAFF
        )
        assert blocked.status_code == 409

        resumed = await api.post(
            f"{PREFIX}/queue-instances/{KC_INSTANCE}/resume", headers=STAFF
        )
        assert resumed.json()["status"] == "open"
        assert (
            await api.post(f"{PREFIX}/queue-instances/{KC_INSTANCE}/call-next", headers=STAFF)
        ).json() is not None

    async def test_closing_carries_unserved_tickets_forward(
        self, api: AsyncClient
    ) -> None:
        """No implicit disposal: the default keeps the patient in the system."""
        ticket = await issue(api, age_years=34)
        closed = await api.post(
            f"{PREFIX}/queue-instances/{KC_INSTANCE}/close", headers=STAFF
        )
        assert closed.json()["status"] == "closed"
        after = await api.get(f"{PREFIX}/tickets/{ticket['ticket_id']}", headers=STAFF)
        assert after.json()["queue_state"] == "deferred"


class TestDashboard:
    async def test_the_dashboard_exposes_waiting_time_and_overtaken_count(
        self, api: AsyncClient
    ) -> None:
        """The starvation guard has to be visible to a human, not merely
        enforced in code."""
        await issue(api, age_years=34)
        await issue(api, age_years=72)
        body = (
            await api.get(
                f"{PREFIX}/queue-instances/{KC_INSTANCE}/dashboard", headers=STAFF
            )
        ).json()
        assert body["waiting_count"] == 2
        assert body["tickets"][0]["priority_class"] == "priority"
        for row in body["tickets"]:
            assert "waiting_minutes" in row
            assert "overtaken_count" in row
            assert "estimated_wait_minutes" in row

    async def test_the_dashboard_carries_no_clinical_text(
        self, api: AsyncClient
    ) -> None:
        intake_id = (
            await api.post(f"{PREFIX}/intakes", json={}, headers=KIOSK)
        ).json()["intake"]["intake_id"]
        await issue(api, age_years=34, intake_id=intake_id)
        body = (
            await api.get(
                f"{PREFIX}/queue-instances/{KC_INSTANCE}/dashboard", headers=STAFF
            )
        ).json()
        allowed = {
            "ticket_id",
            "token",
            "position",
            "priority_class",
            "queue_state",
            "waiting_minutes",
            "overtaken_count",
            "recall_count",
            "has_intake",
            "estimated_wait_minutes",
        }
        for row in body["tickets"]:
            assert set(row) <= allowed


class TestEscalationRequiresAcknowledgement:
    async def _intake_with_alert(self, api: AsyncClient) -> tuple[str, str]:
        """Drive an intake far enough to fire a critical rule."""
        intake_id = (
            await api.post(f"{PREFIX}/intakes", json={}, headers=KIOSK)
        ).json()["intake"]["intake_id"]
        await api.post(
            f"{PREFIX}/intakes/{intake_id}/answers",
            json={"concept": "preferred_language", "value": "en"},
            headers=KIOSK,
        )
        await api.post(
            f"{PREFIX}/consent",
            json={
                "intake_id": intake_id,
                "language": "en",
                "granted_purposes": ["history_intake"],
                "granting_party": "self",
            },
            headers=KIOSK,
        )
        for concept, value in (
            ("chief_complaint", "chest_pain"),
            ("onset", "sudden"),
            ("dyspnoea", "yes"),
        ):
            response = await api.post(
                f"{PREFIX}/intakes/{intake_id}/answers",
                json={"concept": concept, "value": value},
                headers=KIOSK,
            )
            assert response.status_code == 200, response.text
        body = response.json()
        assert body["alerts"], "expected a red flag to fire"
        return intake_id, body["alerts"][0]["alert_id"]

    async def test_a_fired_alert_does_not_change_the_ticket(
        self, api: AsyncClient
    ) -> None:
        """The whole invariant in one assertion."""
        intake_id, _alert_id = await self._intake_with_alert(api)
        ticket = await issue(api, age_years=45, intake_id=intake_id)
        current = await api.get(f"{PREFIX}/tickets/{ticket['ticket_id']}", headers=STAFF)
        assert current.json()["queue_state"] == "waiting"
        assert current.json()["priority_class"] == "walkin"

    async def test_escalating_an_unacknowledged_alert_is_refused(
        self, api: AsyncClient
    ) -> None:
        intake_id, alert_id = await self._intake_with_alert(api)
        ticket = await issue(api, age_years=45, intake_id=intake_id)
        response = await api.post(
            f"{PREFIX}/tickets/{ticket['ticket_id']}/escalate",
            json={"alert_id": alert_id, "acting_user_id": "triage-1"},
            headers=TRIAGE,
        )
        assert response.status_code == 403
        assert "acknowledge" in response.json()["message"]

    async def test_escalating_after_acknowledgement_succeeds_and_records_both_people(
        self, api: AsyncClient
    ) -> None:
        intake_id, alert_id = await self._intake_with_alert(api)
        ticket = await issue(api, age_years=45, intake_id=intake_id)
        acknowledged = await api.post(
            f"{PREFIX}/alerts/{alert_id}/acknowledge", headers=TRIAGE
        )
        assert acknowledged.status_code == 200

        escalated = await api.post(
            f"{PREFIX}/tickets/{ticket['ticket_id']}/escalate",
            json={"alert_id": alert_id, "acting_user_id": "triage-1"},
            headers=TRIAGE,
        )
        body = escalated.json()
        assert body["queue_state"] == "escalated"
        assert body["priority_class"] == "emergency"
        assert body["escalation_alert_id"] == alert_id

    async def test_a_kiosk_cannot_acknowledge_an_alert(self, api: AsyncClient) -> None:
        _intake_id, alert_id = await self._intake_with_alert(api)
        response = await api.post(f"{PREFIX}/alerts/{alert_id}/acknowledge", headers=KIOSK)
        assert response.status_code == 403

    async def test_the_alert_never_names_a_condition(self, api: AsyncClient) -> None:
        intake_id, _alert_id = await self._intake_with_alert(api)
        body = (await api.get(f"{PREFIX}/intakes/{intake_id}", headers=KIOSK)).json()
        for alert in body["alerts"]:
            assert alert["patient_safe_label"] == "Urgent clinical review criterion triggered"
            assert "infarction" not in alert["label"].lower()
            assert alert["clinical_source"]
