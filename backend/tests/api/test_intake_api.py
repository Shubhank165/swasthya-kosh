"""Intake API behaviour: answers, statuses, consent gating, idempotency, roles."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.api.conftest import KIOSK, PHYSICIAN, STAFF, TRIAGE

PREFIX = "/api/v1"


async def start_intake(api: AsyncClient) -> str:
    response = await api.post(f"{PREFIX}/intakes", json={"kiosk_id": "kiosk-1"}, headers=KIOSK)
    assert response.status_code == 201
    return response.json()["intake"]["intake_id"]


async def grant_consent(api: AsyncClient, intake_id: str, language: str = "en") -> str:
    response = await api.post(
        f"{PREFIX}/consent",
        json={
            "intake_id": intake_id,
            "language": language,
            "granted_purposes": ["history_intake", "document_processing"],
            "refused_purposes": ["raw_audio_retention"],
            "granting_party": "self",
        },
        headers=KIOSK,
    )
    assert response.status_code == 201, response.text
    return response.json()["consent_id"]


async def answer(
    api: AsyncClient, intake_id: str, concept: str, value: object = None, **extra: object
) -> dict:
    response = await api.post(
        f"{PREFIX}/intakes/{intake_id}/answers",
        json={"concept": concept, "value": value, **extra},
        headers=KIOSK,
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestAuthentication:
    async def test_an_unauthenticated_request_is_rejected(self, api: AsyncClient) -> None:
        assert (await api.get(f"{PREFIX}/queues")).status_code == 401

    async def test_an_unknown_role_fails_closed(self, api: AsyncClient) -> None:
        response = await api.get(
            f"{PREFIX}/queues", headers={"X-User-Id": "x", "X-User-Role": "wizard"}
        )
        assert response.status_code == 401


class TestIntakeLifecycle:
    async def test_a_new_intake_returns_the_first_question(self, api: AsyncClient) -> None:
        response = await api.post(f"{PREFIX}/intakes", json={}, headers=KIOSK)
        assert response.status_code == 201
        body = response.json()
        assert body["next_step"]["kind"] == "step"
        assert body["next_step"]["concept"] == "preferred_language"
        assert body["intake"]["state"] == "not_started"

    async def test_the_step_explains_why_it_was_chosen(self, api: AsyncClient) -> None:
        intake_id = await start_intake(api)
        step = (await api.get(f"{PREFIX}/intakes/{intake_id}/next-step", headers=KIOSK)).json()
        assert "required field" in step["selection_reason"]

    async def test_answering_returns_the_updated_state_and_the_next_question(
        self, api: AsyncClient
    ) -> None:
        """One round trip per turn: a kiosk on a poor LAN cannot afford two."""
        intake_id = await start_intake(api)
        body = await answer(api, intake_id, "preferred_language", "hi")
        assert body["intake"]["language"] == "hi"
        assert body["next_step"]["concept"] != "preferred_language"
        assert body["next_step"]["language"] == "hi"

    async def test_a_missing_intake_returns_404(self, api: AsyncClient) -> None:
        response = await api.get(f"{PREFIX}/intakes/nope", headers=KIOSK)
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


class TestConsentGating:
    async def test_a_clinical_answer_before_consent_is_refused(
        self, api: AsyncClient
    ) -> None:
        """No history is recorded before the patient has agreed to it."""
        intake_id = await start_intake(api)
        response = await api.post(
            f"{PREFIX}/intakes/{intake_id}/answers",
            json={"concept": "chief_complaint", "value": "fever"},
            headers=KIOSK,
        )
        assert response.status_code == 403
        assert response.json()["code"] == "consent_required"

    async def test_identity_questions_are_allowed_before_consent(
        self, api: AsyncClient
    ) -> None:
        """They are what gets us to the consent decision."""
        intake_id = await start_intake(api)
        await answer(api, intake_id, "preferred_language", "en")
        await answer(api, intake_id, "reporter_role", "self")

    async def test_granting_consent_records_an_immutable_artefact(
        self, api: AsyncClient
    ) -> None:
        """DPDP Act 2023: we must be able to produce exactly what was shown."""
        intake_id = await start_intake(api)
        consent_id = await grant_consent(api, intake_id, "hi")
        artefact = (await api.get(f"{PREFIX}/consent/{consent_id}", headers=KIOSK)).json()
        assert artefact["language"] == "hi"
        assert artefact["granted_purposes"] == ["history_intake", "document_processing"]
        assert artefact["refused_purposes"] == ["raw_audio_retention"]
        assert len(artefact["notice_hash"]) == 64

    async def test_raw_audio_retention_stays_off_without_its_own_grant(
        self, api: AsyncClient
    ) -> None:
        """Recording a voice and keeping it are different asks."""
        intake_id = await start_intake(api)
        await grant_consent(api, intake_id)
        response = await api.get(
            f"{PREFIX}/consent/intake/{intake_id}/audio-retention", headers=KIOSK
        )
        assert response.json() == {"permitted": False}

    async def test_refusing_the_base_purpose_abandons_the_intake_without_error(
        self, api: AsyncClient
    ) -> None:
        """A patient may say no. Their place in the queue is untouched."""
        intake_id = await start_intake(api)
        response = await api.post(
            f"{PREFIX}/consent",
            json={
                "intake_id": intake_id,
                "language": "en",
                "granted_purposes": [],
                "refused_purposes": ["history_intake"],
                "granting_party": "self",
            },
            headers=KIOSK,
        )
        assert response.status_code == 201
        intake = (await api.get(f"{PREFIX}/intakes/{intake_id}", headers=KIOSK)).json()
        assert intake["intake"]["state"] == "abandoned"


class TestAnswerSemantics:
    @pytest.fixture
    async def consented(self, api: AsyncClient) -> str:
        intake_id = await start_intake(api)
        await answer(api, intake_id, "preferred_language", "en")
        await grant_consent(api, intake_id)
        return intake_id

    async def test_no_answer_becomes_unknown_never_absent(
        self, api: AsyncClient, consented: str
    ) -> None:
        """Invariant 4, at the API boundary where it is easiest to get wrong."""
        body = await answer(api, consented, "known_diabetes", None)
        fact = next(f for f in body["intake"]["facts"] if f["concept"] == "known_diabetes")
        assert fact["status"] == "unknown"

    async def test_an_explicit_no_becomes_absent(
        self, api: AsyncClient, consented: str
    ) -> None:
        body = await answer(api, consented, "known_diabetes", "no")
        fact = next(f for f in body["intake"]["facts"] if f["concept"] == "known_diabetes")
        assert fact["status"] == "absent"

    async def test_a_hedged_answer_stays_approximate(
        self, api: AsyncClient, consented: str
    ) -> None:
        """"maybe two weeks" must not become "2 weeks"."""
        body = await answer(
            api,
            consented,
            "complaint_duration",
            {"magnitude": 2, "unit": "weeks"},
            original_expression="maybe two weeks",
            original_language="en",
            source_type="voice",
            segment_id="s1",
            start_ms=0,
            end_ms=1500,
        )
        fact = next(f for f in body["intake"]["facts"] if f["concept"] == "complaint_duration")
        assert fact["certainty"] == "approximate"
        assert fact["temporality"] == "approximate"
        assert fact["value"] == "2 weeks"
        assert fact["original_expression"] == "maybe two weeks"

    async def test_the_verbatim_expression_survives_normalisation(
        self, api: AsyncClient, consented: str
    ) -> None:
        body = await answer(
            api,
            consented,
            "chief_complaint",
            "chest_pain",
            original_expression="seene mein jalan aur saans phoolna",
            original_language="hi",
            source_type="voice",
            segment_id="s1",
            start_ms=0,
            end_ms=2400,
        )
        fact = next(f for f in body["intake"]["facts"] if f["concept"] == "chief_complaint")
        assert fact["original_expression"] == "seene mein jalan aur saans phoolna"
        assert fact["original_language"] == "hi"
        assert fact["value"] == "chest_pain"

    async def test_a_declined_answer_is_recorded_as_a_decline(
        self, api: AsyncClient, consented: str
    ) -> None:
        body = await answer(api, consented, "tobacco_use", None, declined=True)
        assert "tobacco_use" in body["intake"]["declined"]

    async def test_an_option_not_offered_is_rejected(
        self, api: AsyncClient, consented: str
    ) -> None:
        """A value no clinician authored must never enter the record."""
        response = await api.post(
            f"{PREFIX}/intakes/{consented}/answers",
            json={"concept": "chief_complaint", "value": "teleportation_sickness"},
            headers=KIOSK,
        )
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"

    async def test_a_correction_supersedes_rather_than_editing(
        self, api: AsyncClient, consented: str
    ) -> None:
        await answer(api, consented, "known_diabetes", "yes")
        body = await answer(api, consented, "known_diabetes", "no")
        fact = next(f for f in body["intake"]["facts"] if f["concept"] == "known_diabetes")
        assert fact["status"] == "absent"
        assert fact["supersedes"] is not None

    async def test_every_fact_carries_full_provenance(
        self, api: AsyncClient, consented: str
    ) -> None:
        body = await answer(
            api,
            consented,
            "known_diabetes",
            "yes",
            source_type="voice",
            segment_id="s7",
            start_ms=100,
            end_ms=900,
            confidence=0.82,
        )
        fact = next(f for f in body["intake"]["facts"] if f["concept"] == "known_diabetes")
        for key in (
            "status",
            "certainty",
            "temporality",
            "source_type",
            "source_ref",
            "confidence",
            "reported_by",
            "patient_confirmed",
            "physician_verified",
            "recorded_at",
        ):
            assert key in fact
        assert fact["source_ref"]["kind"] == "transcript"
        assert fact["source_ref"]["start_ms"] == 100


class TestIdempotency:
    async def test_a_replayed_answer_does_not_duplicate(self, api: AsyncClient) -> None:
        """A kiosk that lost the LAN and retried must not create a second fact."""
        intake_id = await start_intake(api)
        await answer(api, intake_id, "preferred_language", "en")
        await grant_consent(api, intake_id)

        payload = {"concept": "known_diabetes", "value": "yes"}
        headers = {**KIOSK, "Idempotency-Key": "retry-1"}
        first = await api.post(
            f"{PREFIX}/intakes/{intake_id}/answers", json=payload, headers=headers
        )
        second = await api.post(
            f"{PREFIX}/intakes/{intake_id}/answers", json=payload, headers=headers
        )
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()

        current = (await api.get(f"{PREFIX}/intakes/{intake_id}", headers=KIOSK)).json()
        matches = [f for f in current["intake"]["facts"] if f["concept"] == "known_diabetes"]
        assert len(matches) == 1

    async def test_a_key_reused_with_a_different_body_is_rejected(
        self, api: AsyncClient
    ) -> None:
        """That is a client bug, not a retry, and serving the stored response
        would return the wrong answer."""
        intake_id = await start_intake(api)
        await answer(api, intake_id, "preferred_language", "en")
        await grant_consent(api, intake_id)
        headers = {**KIOSK, "Idempotency-Key": "retry-2"}
        await api.post(
            f"{PREFIX}/intakes/{intake_id}/answers",
            json={"concept": "known_diabetes", "value": "yes"},
            headers=headers,
        )
        clash = await api.post(
            f"{PREFIX}/intakes/{intake_id}/answers",
            json={"concept": "known_diabetes", "value": "no"},
            headers=headers,
        )
        assert clash.status_code == 409
        assert clash.json()["code"] == "idempotency_conflict"

    async def test_a_stale_revision_is_rejected(self, api: AsyncClient) -> None:
        """A kiosk that reconnects with an old view must not clobber a correction
        the patient has since made."""
        intake_id = await start_intake(api)
        await answer(api, intake_id, "preferred_language", "en")
        await grant_consent(api, intake_id)
        stale = await api.post(
            f"{PREFIX}/intakes/{intake_id}/answers",
            json={"concept": "known_diabetes", "value": "yes", "expected_revision": 0},
            headers=KIOSK,
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "conflict"


class TestCoverageEndpoint:
    async def test_coverage_reports_the_gaps_not_just_a_percentage(
        self, api: AsyncClient
    ) -> None:
        intake_id = await start_intake(api)
        body = (await api.get(f"{PREFIX}/intakes/{intake_id}/coverage", headers=KIOSK)).json()
        assert body["percentage"] == 0.0
        assert not body["is_complete"]
        descriptions = [m["description"] for m in body["missing_required"]]
        assert any("allergy" in d for d in descriptions)


class TestRolesOnPhysicianEndpoints:
    async def test_a_kiosk_cannot_verify_a_record(self, api: AsyncClient) -> None:
        intake_id = await start_intake(api)
        response = await api.post(
            f"{PREFIX}/physician/{intake_id}/verify",
            json={"physician_id": "dr-1"},
            headers=KIOSK,
        )
        assert response.status_code == 403

    async def test_staff_cannot_verify_a_record(self, api: AsyncClient) -> None:
        intake_id = await start_intake(api)
        response = await api.post(
            f"{PREFIX}/physician/{intake_id}/verify",
            json={"physician_id": "dr-1"},
            headers=STAFF,
        )
        assert response.status_code == 403

    async def test_a_physician_can_verify(self, api: AsyncClient) -> None:
        intake_id = await start_intake(api)
        await answer(api, intake_id, "preferred_language", "en")
        await grant_consent(api, intake_id)
        await answer(api, intake_id, "known_diabetes", "yes")
        response = await api.post(
            f"{PREFIX}/physician/{intake_id}/verify",
            json={"physician_id": "dr-1"},
            headers=PHYSICIAN,
        )
        assert response.status_code == 200
        facts = response.json()["intake"]["facts"]
        verified = [f for f in facts if f["concept"] == "known_diabetes"]
        assert verified[0]["physician_verified"] is True
        # Verification does not imply the patient confirmed anything.
        assert verified[0]["patient_confirmed"] is False


class TestTerminologyEndpoints:
    async def test_search_returns_candidates_from_every_system_side_by_side(
        self, api: AsyncClient
    ) -> None:
        response = await api.get(
            f"{PREFIX}/terminology/search", params={"q": "jwara"}, headers=STAFF
        )
        assert response.status_code == 200
        body = response.json()
        systems = {r["system"] for r in body["results"]}
        assert "NAMASTE" in systems
        top = body["results"][0]
        assert top["code"] == "AY-JWR"
        assert top["score"] > 0.5

    async def test_a_devanagari_query_finds_the_same_concept(
        self, api: AsyncClient
    ) -> None:
        response = await api.get(
            f"{PREFIX}/terminology/search", params={"q": "संधिगत वात"}, headers=STAFF
        )
        assert "AY-SND-VAT" in {r["code"] for r in response.json()["results"]}

    async def test_dual_codes_are_returned_where_a_mapping_exists(
        self, api: AsyncClient
    ) -> None:
        response = await api.get(
            f"{PREFIX}/terminology/dual-codes",
            params={"system": "NAMASTE", "code": "AY-JWR"},
            headers=STAFF,
        )
        codes = response.json()
        assert codes["NAMASTE"] == "AY-JWR"
        assert codes["ICD11-MMS"] == "MG26"

    async def test_no_mapping_returns_only_the_source_code_rather_than_a_guess(
        self, api: AsyncClient
    ) -> None:
        """An invented mapping is worse than an absent one: it looks
        authoritative and ends up in a discharge summary."""
        response = await api.get(
            f"{PREFIX}/terminology/dual-codes",
            params={"system": "NAMASTE", "code": "AY-AGN"},
            headers=STAFF,
        )
        assert response.json() == {"NAMASTE": "AY-AGN"}

    async def test_fhir_resources_are_served(self, api: AsyncClient) -> None:
        code_system = await api.get(
            f"{PREFIX}/terminology/CodeSystem/NAMASTE", headers=STAFF
        )
        assert code_system.json()["resourceType"] == "CodeSystem"
        concept_map = await api.get(f"{PREFIX}/terminology/ConceptMap", headers=STAFF)
        assert concept_map.json()["resourceType"] == "ConceptMap"
        value_set = await api.get(f"{PREFIX}/terminology/ValueSet/ICD11-MMS", headers=STAFF)
        assert value_set.json()["resourceType"] == "ValueSet"


class TestHealth:
    async def test_health_reports_the_loaded_content(self, api: AsyncClient) -> None:
        body = (await api.get("/health")).json()
        assert body["status"] == "ok"
        assert body["red_flag_rules"] == 24
        assert body["pathways"] >= 6
