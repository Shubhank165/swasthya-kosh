"""The full journey, driven through the API with mock providers.

Definition of done item 3: identity → consent → chief complaint → pathway HPI →
red-flag screen → history sections → document (mock OCR) → contradiction surfaced
→ patient confirmation → report generated → ticket queued → physician
verification, asserting the report content at the end.

Runs on SQLite with the deterministic mocks, so it needs no network and no
Postgres — the point is that the whole system runs end to end in CI.
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient

from tests.api.conftest import KIOSK, PHYSICIAN, STAFF, TRIAGE

PREFIX = "/api/v1"
KC_QUEUE = "q-kc-general"
KC_INSTANCE = "qi-q-kc-general-2026-01-15"


class Journey:
    """A small driver so the test below reads as the story it is testing."""

    def __init__(self, api: AsyncClient) -> None:
        self.api = api
        self.intake_id = ""
        self.last: dict = {}

    async def start(self) -> dict:
        response = await self.api.post(
            f"{PREFIX}/intakes",
            json={"kiosk_id": "kiosk-1", "department_code": "KC"},
            headers=KIOSK,
        )
        assert response.status_code == 201, response.text
        self.last = response.json()
        self.intake_id = self.last["intake"]["intake_id"]
        return self.last

    async def answer(self, concept: str, value: object = None, **extra: object) -> dict:
        response = await self.api.post(
            f"{PREFIX}/intakes/{self.intake_id}/answers",
            json={"concept": concept, "value": value, **extra},
            headers=KIOSK,
        )
        assert response.status_code == 200, f"{concept}: {response.text}"
        self.last = response.json()
        return self.last

    async def consent(self) -> dict:
        response = await self.api.post(
            f"{PREFIX}/consent",
            json={
                "intake_id": self.intake_id,
                "language": "hi",
                "granted_purposes": ["history_intake", "document_processing"],
                "refused_purposes": ["raw_audio_retention"],
                "granting_party": "self",
            },
            headers=KIOSK,
        )
        assert response.status_code == 201, response.text
        return response.json()

    async def next_step(self) -> dict:
        response = await self.api.get(
            f"{PREFIX}/intakes/{self.intake_id}/next-step", headers=KIOSK
        )
        return response.json()

    async def report(self) -> dict:
        response = await self.api.get(
            f"{PREFIX}/intakes/{self.intake_id}/report", headers=PHYSICIAN
        )
        assert response.status_code == 200, response.text
        return response.json()

    async def drive_to_completion(self, limit: int = 120) -> int:
        """Answer whatever is asked until the machine says Complete."""
        for asked in range(limit):
            step = await self.next_step()
            if step["kind"] == "complete":
                return asked
            await self.answer(step["concept"], _plausible(step))
        raise AssertionError(f"intake did not complete within {limit} questions")


def _plausible(step: dict) -> object:
    """A valid answer for whatever the step asks."""
    shape = step["answer"]["type"]
    options = [o for o in step["answer"]["options"] if o != "unknown"]
    if shape in {"single_choice", "confirmation"}:
        return options[0] if options else "yes"
    if shape == "multi_choice":
        return [options[0]] if options else ["unknown"]
    if shape == "scale":
        return 5
    if shape == "duration":
        return {"magnitude": 3, "unit": "days"}
    if shape == "quantity":
        return {"magnitude": 34, "unit": step["answer"]["unit"] or "unit"}
    if shape == "date":
        return "2019"
    if shape == "yes_no_unknown":
        return "no"
    return "recorded"


@pytest.fixture
async def journey(api: AsyncClient) -> Journey:
    return Journey(api)


async def apply_document_fact(
    api: AsyncClient,
    intake_id: str,
    *,
    concept: str,
    display: str,
    text: str,
    confidence: float,
) -> None:
    """Fold a document-derived fact into an intake.

    Uses `IntakeService.apply_document_extraction` — the same entry point the
    async OCR worker will call — against the same database the app is using.
    """
    from app.core.config import Settings
    from app.core.content import get_clinical_content
    from app.domain.clinical.enums import (
        Certainty,
        FactStatus,
        ReporterRole,
        Section,
        SourceType,
        Temporality,
    )
    from app.domain.clinical.fact import ClinicalFact
    from app.domain.clinical.provenance import (
        ConceptRef,
        DocumentId,
        FactId,
        SourceRef,
        TextValue,
    )
    from app.repositories.alerts import AlertRepository
    from app.repositories.consent import ConsentRepository
    from app.repositories.intakes import IntakeRepository
    from app.services.intake import IntakeService

    fact = ClinicalFact(
        fact_id=FactId(f"doc-fact-{concept}"),
        concept=ConceptRef(concept, display=display),
        status=FactStatus.PRESENT,
        certainty=Certainty.REPORTED,
        temporality=Temporality.HISTORICAL,
        source_type=SourceType.DOCUMENT,
        source_ref=SourceRef.from_document(DocumentId("Discharge_summary_2.jpg"), page=1),
        confidence=confidence,
        reported_by=ReporterRole.STAFF,
        recorded_at=api.clock.now(),  # type: ignore[attr-defined]
        section=Section.PAST_MEDICAL,
        value=TextValue(text),
    )

    async with api.sessions() as session:  # type: ignore[attr-defined]
        service = IntakeService(
            intakes=IntakeRepository(session),
            alerts=AlertRepository(session),
            consent=ConsentRepository(session),
            content=get_clinical_content(),
            bus=api.bus,  # type: ignore[attr-defined]
            settings=Settings(environment="test"),
            clock=api.clock,  # type: ignore[attr-defined]
        )
        await service.apply_document_extraction(
            intake_id,
            document_id="Discharge_summary_2.jpg",
            facts=(fact,),
            low_confidence=False,
            page_count=1,
            kind="discharge_summary",
        )
        await session.commit()


class TestFullIntakeJourney:
    async def test_the_whole_story(self, api: AsyncClient, journey: Journey) -> None:
        # --- identity -------------------------------------------------------
        first = await journey.start()
        assert first["next_step"]["concept"] == "preferred_language"
        assert first["intake"]["state"] == "not_started"

        await journey.answer("preferred_language", "hi")
        assert journey.last["next_step"]["language"] == "hi"

        await journey.answer("reporter_role", "self")
        await journey.answer("age", {"magnitude": 58, "unit": "years"})
        await journey.answer("sex", "male")

        # --- consent --------------------------------------------------------
        # No clinical fact may be recorded before this point.
        blocked = await api.post(
            f"{PREFIX}/intakes/{journey.intake_id}/answers",
            json={"concept": "chief_complaint", "value": "chest_pain"},
            headers=KIOSK,
        )
        assert blocked.status_code == 403

        artefact = await journey.consent()
        assert artefact["granted_purposes"] == ["history_intake", "document_processing"]
        assert "raw_audio_retention" in artefact["refused_purposes"]

        # A male patient is never asked about pregnancy; the record says why.
        state = (await api.get(f"{PREFIX}/intakes/{journey.intake_id}", headers=KIOSK)).json()
        pregnancy = [f for f in state["intake"]["facts"] if f["concept"] == "pregnancy"]
        assert pregnancy and pregnancy[0]["status"] == "not_applicable"

        # --- chief complaint, in the patient's own words ----------------------
        await journey.answer(
            "chief_complaint",
            "chest_pain",
            original_expression="seene mein jalan aur saans phoolna",
            original_language="hi",
            source_type="voice",
            segment_id="seg-1",
            start_ms=0,
            end_ms=2400,
            confidence=0.91,
        )
        assert journey.last["intake"]["active_pathway"] == "chest_pain"

        # --- pathway HPI ------------------------------------------------------
        await journey.answer("onset", "sudden")
        await journey.answer("severity", 8)
        await journey.answer("radiation", "to_left_arm")

        # --- red-flag screen --------------------------------------------------
        await journey.answer("dyspnoea", "yes")
        alerts = journey.last["alerts"]
        assert alerts, "expected an urgent review criterion to trigger"
        rule_ids = {a["rule_id"] for a in alerts}
        assert "acute_chest_pain_with_dyspnoea" in rule_ids
        for alert in alerts:
            assert alert["patient_safe_label"] == "Urgent clinical review criterion triggered"
            assert alert["clinical_source"]
            assert alert["is_open"], "an alert starts open and awaiting a human"

        # --- the alert has changed nothing about the queue --------------------
        ticket = (
            await api.post(
                f"{PREFIX}/queues/{KC_QUEUE}/tickets",
                json={
                    "instance_id": KC_INSTANCE,
                    "intake_id": journey.intake_id,
                    "age_years": 58,
                },
                headers=STAFF,
            )
        ).json()
        assert ticket["queue_state"] == "waiting"
        assert ticket["priority_class"] == "walkin"

        # --- history sections, including a denial that will conflict ----------
        await journey.answer("known_diabetes", "no")

        # --- document upload and mock OCR -------------------------------------
        upload = await api.post(
            f"{PREFIX}/intakes/{journey.intake_id}/documents",
            files={"file": ("Discharge_summary_2.jpg", io.BytesIO(b"scan"), "image/jpeg")},
            params={"kind": "discharge_summary"},
            headers=KIOSK,
        )
        assert upload.status_code == 200, upload.text
        assert upload.json()["intake"]["documents"]

        # --- finish the remaining history -------------------------------------
        await journey.drive_to_completion()

        # --- patient confirmation ----------------------------------------------
        confirmed = await api.post(
            f"{PREFIX}/intakes/{journey.intake_id}/confirm",
            json={"corrections": []},
            headers=KIOSK,
        )
        assert confirmed.status_code == 200, confirmed.text
        body = confirmed.json()
        assert body["coverage"]["is_complete"]
        assert body["intake"]["state"] in {"ready", "awaiting_confirmation"}

        # Confirmation raised certainty but not verification.
        complaint = next(
            f for f in body["intake"]["facts"] if f["concept"] == "chief_complaint"
        )
        assert complaint["patient_confirmed"] is True
        assert complaint["physician_verified"] is False

        # --- the report ---------------------------------------------------------
        report = await journey.report()
        text = report["rendered_text"]

        assert text.startswith("DRAFT PRE-CONSULTATION INTAKE")
        assert "no diagnosis and no clinical advice" in text
        # The patient's own words survived the whole pipeline.
        assert "seene mein jalan aur saans phoolna" in text
        assert "CHIEF COMPLAINT" in text
        assert "HISTORY OF PRESENTING ILLNESS" in text
        assert "SAFETY" in text
        assert "Urgent clinical review criterion triggered" in text
        # Nothing that reads as a diagnosis or a piece of advice.
        for forbidden in ("myocardial infarction", "heart attack", "you have", "we recommend"):
            assert forbidden not in text.lower()
        assert report["coverage_percentage"] == 100.0
        assert report["physician_verified"] is False

        # Every rendered line links back to the facts behind it.
        lines = [line for section in report["sections"] for line in section["lines"]]
        assert lines
        assert all(line["fact_ids"] for line in lines)

        # --- evidence click-through ---------------------------------------------
        evidence = await api.get(
            f"{PREFIX}/intakes/{journey.intake_id}/facts/"
            f"{complaint['fact_id']}/evidence",
            headers=PHYSICIAN,
        )
        assert evidence.status_code == 200
        detail = evidence.json()
        assert detail["original_expression"] == "seene mein jalan aur saans phoolna"
        assert detail["revisions"]

        # --- triage acknowledges, then escalates ---------------------------------
        alert_id = alerts[0]["alert_id"]
        refused = await api.post(
            f"{PREFIX}/tickets/{ticket['ticket_id']}/escalate",
            json={"alert_id": alert_id, "acting_user_id": "triage-1"},
            headers=TRIAGE,
        )
        assert refused.status_code == 403, "escalation must require acknowledgement"

        await api.post(f"{PREFIX}/alerts/{alert_id}/acknowledge", headers=TRIAGE)
        escalated = await api.post(
            f"{PREFIX}/tickets/{ticket['ticket_id']}/escalate",
            json={"alert_id": alert_id, "acting_user_id": "triage-1"},
            headers=TRIAGE,
        )
        assert escalated.json()["queue_state"] == "escalated"
        assert escalated.json()["priority_class"] == "emergency"

        # --- physician verification ------------------------------------------------
        verified = await api.post(
            f"{PREFIX}/physician/{journey.intake_id}/verify",
            json={"physician_id": "dr-1"},
            headers=PHYSICIAN,
        )
        assert verified.status_code == 200
        assert all(
            f["physician_verified"]
            for f in verified.json()["intake"]["facts"]
            if f["status"] not in {"not_asked", "not_applicable"}
        )

        # --- the consultation runs ---------------------------------------------------
        await api.post(f"{PREFIX}/tickets/{ticket['ticket_id']}/start", headers=PHYSICIAN)
        completed = await api.post(
            f"{PREFIX}/tickets/{ticket['ticket_id']}/complete", headers=PHYSICIAN
        )
        assert completed.json()["queue_state"] == "completed"


class TestAttendantReportedJourney:
    async def test_an_attendant_reported_history_is_marked_as_such(
        self, api: AsyncClient, journey: Journey
    ) -> None:
        """A son answering for his mother is weaker evidence than she is, and the
        physician must be able to see which."""
        await journey.start()
        await journey.answer("preferred_language", "hi")
        await journey.answer("reporter_role", "family_attendant")
        await journey.consent()
        await journey.answer(
            "chief_complaint",
            "joint_pain",
            original_expression="maa ko jodon mein dard hai",
            original_language="hi",
            source_type="voice",
            segment_id="s1",
            start_ms=0,
            end_ms=1800,
        )
        fact = next(
            f for f in journey.last["intake"]["facts"] if f["concept"] == "chief_complaint"
        )
        assert fact["reported_by"] == "family_attendant"

        await journey.drive_to_completion()
        report = await journey.report()
        assert "reported by attendant" in report["rendered_text"]


class TestAbandonedJourney:
    async def test_an_abandoned_intake_keeps_what_was_captured(
        self, api: AsyncClient, journey: Journey
    ) -> None:
        """A patient who walks away mid-history leaves a partial record, not a
        deleted one — and the report says exactly what is missing."""
        await journey.start()
        await journey.answer("preferred_language", "en")
        await journey.consent()
        await journey.answer("chief_complaint", "fever")

        report = await journey.report()
        assert report["coverage_percentage"] < 100.0
        assert report["unresolved"], "an incomplete intake must say what it is missing"
        text = report["rendered_text"]
        assert "UNRESOLVED" in text
        assert "not asked" in text


class TestContradictionSurfacing:
    async def test_a_denial_against_a_prior_record_is_surfaced_unresolved(
        self, api: AsyncClient, journey: Journey
    ) -> None:
        """The conflict is the finding. The system reports both sides and stops.

        The document fact is injected through `apply_document_extraction`, which
        is the same entry point the async OCR worker will use — this build ships
        the mock provider, so the test stands in for the worker.
        """
        await journey.start()
        await journey.answer("preferred_language", "en")
        await journey.consent()
        await journey.answer("chief_complaint", "fever")
        await journey.answer("known_diabetes", "no")

        await apply_document_fact(
            api,
            journey.intake_id,
            concept="known_diabetes",
            display="Diabetes",
            text="Type 2 Diabetes Mellitus",
            confidence=0.94,
        )

        report = await journey.report()
        assert report["conflicts"], "the disagreement must be surfaced"
        conflict = report["conflicts"][0]
        assert conflict["concept"] == "known_diabetes"
        assert conflict["resolution"] == "Physician verification required"
        assert conflict["reported_today"]["statement"] == "denies Diabetes"
        assert "Type 2 Diabetes Mellitus" in conflict["from_record"]["statement"]
        # Neither side is presented as the correct one.
        assert conflict["reported_today"]["source_type"] == "touch"
        assert conflict["from_record"]["source_type"] == "document"
        assert conflict["from_record"]["confidence"] == 0.94

        text = report["rendered_text"]
        assert "INFORMATION CONFLICT" in text
        assert "Physician verification required" in text

    async def test_the_patient_s_own_answer_is_not_overwritten_by_the_document(
        self, api: AsyncClient, journey: Journey
    ) -> None:
        """A scan must never silently replace what the patient said."""
        await journey.start()
        await journey.answer("preferred_language", "en")
        await journey.consent()
        await journey.answer("chief_complaint", "fever")
        await journey.answer("known_diabetes", "no")

        await apply_document_fact(
            api,
            journey.intake_id,
            concept="known_diabetes",
            display="Diabetes",
            text="Type 2 Diabetes Mellitus",
            confidence=0.94,
        )

        state = (
            await api.get(f"{PREFIX}/intakes/{journey.intake_id}", headers=KIOSK)
        ).json()
        live = next(f for f in state["intake"]["facts"] if f["concept"] == "known_diabetes")
        assert live["status"] == "absent", "the patient's denial stands"
        assert live["source_type"] == "touch"
