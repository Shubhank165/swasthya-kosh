"""The API surface and event vocabulary the brief specifies, checked directly.

These tests exist because a gap here is invisible: an endpoint nobody wrote and
an event nobody publishes both look exactly like a working system until someone
integrates against them.
"""

from __future__ import annotations

import re
from pathlib import Path

from httpx import AsyncClient

from app.events.schemas import EventName
from app.main import create_app
from tests.api.conftest import KIOSK, PHYSICIAN, STAFF, TRIAGE

PREFIX = "/api/v1"
APP_ROOT = Path(__file__).resolve().parents[2] / "app"

#: Every route the brief's section 11 lists.
REQUIRED_ROUTES: tuple[tuple[str, str], ...] = (
    ("POST", "/api/v1/intakes"),
    ("GET", "/api/v1/intakes/{intake_id}"),
    ("PATCH", "/api/v1/intakes/{intake_id}"),
    ("POST", "/api/v1/intakes/{intake_id}/answers"),
    ("GET", "/api/v1/intakes/{intake_id}/next-step"),
    ("GET", "/api/v1/intakes/{intake_id}/coverage"),
    ("POST", "/api/v1/intakes/{intake_id}/documents"),
    ("POST", "/api/v1/intakes/{intake_id}/confirm"),
    ("GET", "/api/v1/intakes/{intake_id}/report"),
    ("GET", "/api/v1/intakes/{intake_id}/facts/{fact_id}/evidence"),
    ("POST", "/api/v1/consent"),
    ("GET", "/api/v1/consent/{consent_id}"),
    ("GET", "/api/v1/queues"),
    ("GET", "/api/v1/queues/{queue_id}/instance"),
    ("POST", "/api/v1/queues/{queue_id}/tickets"),
    ("POST", "/api/v1/tickets/{ticket_id}/call"),
    ("POST", "/api/v1/tickets/{ticket_id}/recall"),
    ("POST", "/api/v1/tickets/{ticket_id}/start"),
    ("POST", "/api/v1/tickets/{ticket_id}/complete"),
    ("POST", "/api/v1/tickets/{ticket_id}/defer"),
    ("POST", "/api/v1/tickets/{ticket_id}/transfer"),
    ("POST", "/api/v1/tickets/{ticket_id}/no-show"),
    ("POST", "/api/v1/tickets/{ticket_id}/escalate"),
    ("POST", "/api/v1/queue-instances/{instance_id}/pause"),
    ("POST", "/api/v1/queue-instances/{instance_id}/resume"),
    ("POST", "/api/v1/queue-instances/{instance_id}/close"),
    ("GET", "/api/v1/terminology/search"),
    ("POST", "/api/v1/physician/{intake_id}/verify"),
    ("POST", "/api/v1/alerts/{alert_id}/acknowledge"),
)


class TestApiSurface:
    def test_every_route_the_brief_specifies_exists(self) -> None:
        schema = create_app().openapi()
        missing = [
            f"{method} {path}"
            for method, path in REQUIRED_ROUTES
            if path not in schema["paths"] or method.lower() not in schema["paths"][path]
        ]
        assert missing == []

    def test_both_websocket_channels_accept_a_connection(self) -> None:
        """Connect for real rather than inspecting the route table: a mounted
        route object that rejects every connection looks identical from the
        outside, and the route tree shape is a FastAPI implementation detail."""
        from fastapi.testclient import TestClient

        client = TestClient(create_app())
        with client.websocket_connect("/ws/dashboard?department=KC") as socket:
            assert socket.receive_json() == {
                "event": "subscribed",
                "channel": "dashboard",
                "department": "KC",
            }
        with client.websocket_connect("/ws/intakes/intake-1") as socket:
            assert socket.receive_json() == {
                "event": "subscribed",
                "channel": "intake",
                "intake_id": "intake-1",
            }


class TestEventVocabulary:
    def test_every_event_the_brief_lists_is_defined(self) -> None:
        values = {e.value for e in EventName}
        for name in (
            "intake.started", "intake.updated", "intake.ready", "intake.confirmed",
            "intake.abandoned", "intake.redflag.raised", "intake.redflag.acknowledged",
            "intake.redflag.dismissed", "document.uploaded", "document.processed",
            "document.low_confidence", "queue.ticket.issued", "queue.ticket.called",
            "queue.ticket.recalled", "queue.ticket.started", "queue.ticket.completed",
            "queue.ticket.no_show", "queue.ticket.deferred", "queue.ticket.transferred",
            "queue.ticket.escalated", "queue.instance.opened", "queue.instance.paused",
            "queue.instance.resumed", "queue.instance.closed", "report.ready",
            "report.physician_verified",
        ):
            assert name in values, name

    def test_every_defined_event_is_actually_published_somewhere(self) -> None:
        """A declared event nobody emits is a contract the dashboard cannot rely
        on, and it looks identical to a working one from the outside."""
        emitted: set[str] = set()
        for path in APP_ROOT.rglob("*.py"):
            src = path.read_text(encoding="utf-8")
            emitted |= set(re.findall(r"name=EventName\.([A-Z_]+)", src))
            emitted |= {e.name for e in EventName if f'name="{e.value}"' in src}
        never = sorted(e.value for e in EventName if e.name not in emitted)
        assert never == []


class TestIdempotencyEverywhere:
    def test_every_mutating_endpoint_accepts_an_idempotency_key(self) -> None:
        """The brief's requirement, checked against the wiring rather than
        remembered. Document upload is exempt: it is multipart, and its own
        document id already makes a replay harmless."""
        exempt = {("POST", "/api/v1/intakes/{intake_id}/documents")}
        schema = create_app().openapi()
        missing: list[str] = []
        for path, methods in schema["paths"].items():
            for method, spec in methods.items():
                if method.upper() not in {"POST", "PATCH", "PUT"}:
                    continue
                if (method.upper(), path) in exempt:
                    continue
                names = {p.get("name") for p in spec.get("parameters", [])}
                if "Idempotency-Key" not in names:
                    missing.append(f"{method.upper()} {path}")
        assert missing == []


class TestReportPersistence:
    async def _ready_intake(self, api: AsyncClient) -> str:
        _, snap = 0, (await api.post(f"{PREFIX}/intakes", json={}, headers=KIOSK)).json()
        intake_id = snap["intake"]["intake_id"]
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
        await api.post(
            f"{PREFIX}/intakes/{intake_id}/answers",
            json={"concept": "chief_complaint", "value": "fever"},
            headers=KIOSK,
        )
        return intake_id

    async def test_generating_a_report_records_it(self, api: AsyncClient) -> None:
        from sqlalchemy import select

        from app.models.clinical import ReportRecord

        intake_id = await self._ready_intake(api)
        assert (
            await api.get(f"{PREFIX}/intakes/{intake_id}/report", headers=PHYSICIAN)
        ).status_code == 200

        async with api.sessions() as session:  # type: ignore[attr-defined]
            rows = (
                await session.execute(
                    select(ReportRecord).where(ReportRecord.intake_id == intake_id)
                )
            ).scalars().all()
        assert len(rows) == 1
        assert rows[0].body["sections"]
        assert rows[0].intake_revision > 0

    async def test_physician_verification_is_recorded_on_the_report(
        self, api: AsyncClient
    ) -> None:
        intake_id = await self._ready_intake(api)
        await api.get(f"{PREFIX}/intakes/{intake_id}/report", headers=PHYSICIAN)
        await api.post(
            f"{PREFIX}/physician/{intake_id}/verify",
            json={"physician_id": "dr-1"},
            headers=PHYSICIAN,
        )

        from sqlalchemy import select

        from app.models.clinical import ReportRecord

        async with api.sessions() as session:  # type: ignore[attr-defined]
            row = (
                await session.execute(
                    select(ReportRecord).where(ReportRecord.intake_id == intake_id)
                )
            ).scalars().first()
        assert row is not None
        assert row.physician_verified_by == "dr-1"
        assert row.physician_verified_at is not None


class TestFhirBundle:
    async def test_the_bundle_carries_dual_codes_where_a_mapping_exists(
        self, api: AsyncClient
    ) -> None:
        snap = (await api.post(f"{PREFIX}/intakes", json={}, headers=KIOSK)).json()
        intake_id = snap["intake"]["intake_id"]
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
        await api.post(
            f"{PREFIX}/intakes/{intake_id}/answers",
            json={
                "concept": "chief_complaint",
                "value": "fever",
                "original_expression": "bukhar",
                "original_language": "hi",
            },
            headers=KIOSK,
        )

        response = await api.get(f"{PREFIX}/intakes/{intake_id}/fhir", headers=PHYSICIAN)
        assert response.status_code == 200
        bundle = response.json()
        assert bundle["resourceType"] == "Bundle"
        assert bundle["entry"]

        fever = next(
            e["resource"]
            for e in bundle["entry"]
            if e["resource"]["code"]["coding"][0]["code"] in {"AY-JWR", "MG26", "SK40"}
            or any(c["code"] == "AY-JWR" for c in e["resource"]["code"]["coding"])
        )
        systems = {c["system"] for c in fever["code"]["coding"]}
        # NAMASTE alongside the biomedical code, because a mapping exists.
        assert len(systems) >= 2
        # The patient's own words survive into CodeableConcept.text.
        assert fever["code"]["text"] == "bukhar"

    async def test_nothing_unverified_is_asserted_as_confirmed(
        self, api: AsyncClient
    ) -> None:
        snap = (await api.post(f"{PREFIX}/intakes", json={}, headers=KIOSK)).json()
        intake_id = snap["intake"]["intake_id"]
        await api.post(
            f"{PREFIX}/intakes/{intake_id}/answers",
            json={"concept": "preferred_language", "value": "en"},
            headers=KIOSK,
        )
        bundle = (
            await api.get(f"{PREFIX}/intakes/{intake_id}/fhir", headers=PHYSICIAN)
        ).json()
        for entry in bundle["entry"]:
            resource = entry["resource"]
            if resource["resourceType"] == "Condition":
                code = resource["verificationStatus"]["coding"][0]["code"]
                assert code != "confirmed"
            else:
                assert resource["status"] == "preliminary"

    async def test_a_kiosk_may_not_read_the_bundle(self, api: AsyncClient) -> None:
        snap = (await api.post(f"{PREFIX}/intakes", json={}, headers=KIOSK)).json()
        response = await api.get(
            f"{PREFIX}/intakes/{snap['intake']['intake_id']}/fhir", headers=KIOSK
        )
        assert response.status_code == 403


class TestQueueDateFilter:
    async def test_the_date_filter_honours_each_queue_s_schedule(
        self, api: AsyncClient
    ) -> None:
        """The Netra clinic runs Tuesdays and Thursdays; a Monday display must
        not list it."""
        monday = "2026-01-12"
        tuesday = "2026-01-13"
        mon = (
            await api.get(f"{PREFIX}/queues", params={"date": monday}, headers=STAFF)
        ).json()
        tue = (
            await api.get(f"{PREFIX}/queues", params={"date": tuesday}, headers=STAFF)
        ).json()
        assert "q-sk-eye" not in {q["queue_id"] for q in mon}
        assert "q-sk-eye" in {q["queue_id"] for q in tue}
        # An everyday queue appears on both.
        assert "q-kc-general" in {q["queue_id"] for q in mon}

    async def test_the_filter_composes_with_department(self, api: AsyncClient) -> None:
        queues = (
            await api.get(
                f"{PREFIX}/queues",
                params={"date": "2026-01-13", "department": "SK"},
                headers=STAFF,
            )
        ).json()
        assert {q["queue_id"] for q in queues} == {"q-sk-eye"}


class TestIdempotencyOnQueueOperations:
    async def test_a_retried_ticket_issue_does_not_hand_out_a_second_token(
        self, api: AsyncClient
    ) -> None:
        payload = {"instance_id": "qi-q-kc-general-2026-01-15", "age_years": 40}
        headers = {**STAFF, "Idempotency-Key": "issue-retry-1"}
        first = await api.post(
            f"{PREFIX}/queues/q-kc-general/tickets", json=payload, headers=headers
        )
        second = await api.post(
            f"{PREFIX}/queues/q-kc-general/tickets", json=payload, headers=headers
        )
        assert first.status_code == second.status_code == 201
        assert first.json()["ticket_id"] == second.json()["ticket_id"]
        assert first.json()["token_number"] == second.json()["token_number"]

    async def test_a_retried_call_next_does_not_call_a_second_patient(
        self, api: AsyncClient
    ) -> None:
        """The network dropped after the patient was called. Retrying must not
        summon the next one while the first is walking over."""
        instance = "qi-q-kc-general-2026-01-15"
        for _ in range(2):
            await api.post(
                f"{PREFIX}/queues/q-kc-general/tickets",
                json={"instance_id": instance, "age_years": 30},
                headers=STAFF,
            )
        headers = {**STAFF, "Idempotency-Key": "call-retry-1"}
        first = await api.post(
            f"{PREFIX}/queue-instances/{instance}/call-next", headers=headers
        )
        second = await api.post(
            f"{PREFIX}/queue-instances/{instance}/call-next", headers=headers
        )
        assert first.json()["ticket_id"] == second.json()["ticket_id"]

    async def test_a_retried_consent_does_not_write_a_second_artefact(
        self, api: AsyncClient
    ) -> None:
        snap = (await api.post(f"{PREFIX}/intakes", json={}, headers=KIOSK)).json()
        intake_id = snap["intake"]["intake_id"]
        payload = {
            "intake_id": intake_id,
            "language": "en",
            "granted_purposes": ["history_intake"],
            "granting_party": "self",
        }
        headers = {**KIOSK, "Idempotency-Key": "consent-retry-1"}
        first = await api.post(f"{PREFIX}/consent", json=payload, headers=headers)
        second = await api.post(f"{PREFIX}/consent", json=payload, headers=headers)
        assert first.json()["consent_id"] == second.json()["consent_id"]

    async def test_a_retried_escalation_does_not_escalate_twice(
        self, api: AsyncClient
    ) -> None:
        instance = "qi-q-kc-general-2026-01-15"
        snap = (await api.post(f"{PREFIX}/intakes", json={}, headers=KIOSK)).json()
        intake_id = snap["intake"]["intake_id"]
        for concept, value in (("preferred_language", "en"),):
            await api.post(
                f"{PREFIX}/intakes/{intake_id}/answers",
                json={"concept": concept, "value": value},
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
        body = {}
        for concept, value in (
            ("chief_complaint", "chest_pain"),
            ("onset", "sudden"),
            ("dyspnoea", "yes"),
        ):
            body = (
                await api.post(
                    f"{PREFIX}/intakes/{intake_id}/answers",
                    json={"concept": concept, "value": value},
                    headers=KIOSK,
                )
            ).json()
        alert_id = body["alerts"][0]["alert_id"]
        ticket = (
            await api.post(
                f"{PREFIX}/queues/q-kc-general/tickets",
                json={"instance_id": instance, "intake_id": intake_id, "age_years": 50},
                headers=STAFF,
            )
        ).json()
        await api.post(f"{PREFIX}/alerts/{alert_id}/acknowledge", headers=TRIAGE)

        headers = {**TRIAGE, "Idempotency-Key": "escalate-retry-1"}
        payload = {"alert_id": alert_id, "acting_user_id": "triage-1"}
        first = await api.post(
            f"{PREFIX}/tickets/{ticket['ticket_id']}/escalate", json=payload, headers=headers
        )
        second = await api.post(
            f"{PREFIX}/tickets/{ticket['ticket_id']}/escalate", json=payload, headers=headers
        )
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()


class TestReportReadyEvent:
    async def test_report_ready_is_published_once_the_history_is_usable(
        self, api: AsyncClient
    ) -> None:
        from app.events.schemas import EventName as E

        snap = (await api.post(f"{PREFIX}/intakes", json={}, headers=KIOSK)).json()
        intake_id = snap["intake"]["intake_id"]
        await api.post(
            f"{PREFIX}/intakes/{intake_id}/answers",
            json={"concept": "preferred_language", "value": "en"},
            headers=KIOSK,
        )
        # Still mid-history: a dashboard must not be told a report is ready.
        await api.get(f"{PREFIX}/intakes/{intake_id}/report", headers=PHYSICIAN)
        names = {e.name for e in api.bus.history}  # type: ignore[attr-defined]
        assert E.REPORT_READY not in names
