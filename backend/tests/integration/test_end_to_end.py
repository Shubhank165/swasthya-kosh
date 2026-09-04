"""The whole path, through the HTTP API — §13.3.

Ingest a kiosk payload, upload a prescription, let the OCR pass run, watch the
contradiction surface, read the report, export the FHIR bundle. Every one of
those steps has its own test elsewhere; none of them proves the pipeline is
connected, and a build where each piece works and the wiring does not is the
build that fails on stage.

Deliberately over the API rather than over the services. The services are called
by routers, by dependency-injected repositories, inside a tenant context set from
an auth token — and that is the assembly that ships. A test that calls
`IngestService.ingest` directly skips authentication, tenancy, serialisation and
the background task, which is most of what there is to get wrong.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import KIOSK_HEADERS, PHYSICIAN_HEADERS, STAFF_HEADERS


@pytest.fixture
def journey(
    app_client: Any, kiosk_payload: dict[str, Any], ocr_images: dict[str, bytes]
) -> dict[str, Any]:
    """One patient's complete visit.

    A Hindi intake naming "Metformin", then a photographed prescription reading
    `900.2 mg` — the digit the OCR benchmark actually got wrong. The two are the
    same drug under different field ids, which is exactly the case the alignment
    pass exists to make comparable.
    """
    ingest = app_client.post(
        "/api/v1/intakes/ingest", json=kiosk_payload, headers=KIOSK_HEADERS
    )
    assert ingest.status_code == 200, ingest.text
    intake_id = ingest.json()["intake_id"]

    upload = app_client.post(
        f"/api/v1/intakes/{intake_id}/documents",
        files={
            "file": (
                "prescription.jpg",
                ocr_images["prescription_lowconf"],
                "image/jpeg",
            )
        },
        data={"kind": "prescription"},
        headers=KIOSK_HEADERS,
    )
    assert upload.status_code == 202, upload.text

    return {"intake_id": intake_id, "ingest": ingest.json(), "upload": upload.json()}


class TestIngest:
    def test_the_kiosk_payload_is_accepted_and_needs_no_repair(
        self, journey: dict[str, Any]
    ) -> None:
        body = journey["ingest"]
        assert body["repaired"] is False
        assert body["needs_manual_review"] is False
        assert body["status"] == "complete"
        # The useful half of the response: the fields the device could not
        # settle, so staff can fill them before the consultation.
        assert "severity" in body["unresolved_fields"]

    def test_the_upload_returns_immediately(self, journey: dict[str, Any]) -> None:
        """202 and a document id.

        Nothing about the patient's experience waits on a model. They have
        already answered the questions and gone to sit down.
        """
        assert journey["upload"]["document_id"]
        assert journey["upload"]["status"] in {"received", "processing", "processed"}


class TestTheDocumentIsRead:
    def test_ocr_ran_and_the_document_is_attached_to_the_intake(
        self, app_client: Any, journey: dict[str, Any]
    ) -> None:
        """The background task ran; `TestClient` drains it before returning."""
        listed = app_client.get(
            f"/api/v1/intakes/{journey['intake_id']}/documents", headers=STAFF_HEADERS
        )
        assert listed.status_code == 200, listed.text
        documents = listed.json()
        assert len(documents) == 1
        assert documents[0]["status"] == "processed"
        assert documents[0]["low_confidence"] is True

    def test_the_low_confidence_dose_is_marked_rather_than_trusted(
        self, app_client: Any, journey: dict[str, Any]
    ) -> None:
        """`900.2` for `100.2`. Read, kept, and flagged for a human to check."""
        record = app_client.get(
            f"/api/v1/intakes/{journey['intake_id']}", headers=STAFF_HEADERS
        ).json()
        doses = [
            fact
            for fact in record["facts"]
            if fact["channel"] == "document" and "metformin" in fact["field_id"]
        ]
        assert doses, "the prescription produced no medication fact"
        assert all(fact["needs_verification"] for fact in doses)
        assert any("900.2" in (fact["rendered"] or "") for fact in doses)


class TestTheContradictionSurfaces:
    def test_the_spoken_dose_and_the_printed_dose_are_compared(
        self, app_client: Any, journey: dict[str, Any]
    ) -> None:
        """The point of the whole pipeline.

        The patient said "Metformin". The paper says "900.2 mg BD". Different
        field ids, same drug, and the physician needs to be told they disagree —
        not told the patient forgot to mention a medicine they did mention.
        """
        record = app_client.get(
            f"/api/v1/intakes/{journey['intake_id']}", headers=STAFF_HEADERS
        ).json()
        conflicts = {c["field_id"] for c in record["contradictions"]}
        assert "medication_metformin" in conflicts

        metformin = next(
            c for c in record["contradictions"] if c["field_id"] == "medication_metformin"
        )
        assert metformin["reported_today"] is not None, (
            "the voice answer was not aligned onto the document field, so the "
            "prescription reads as a medicine the patient never mentioned"
        )
        assert metformin["resolution"]

    def test_the_record_asks_for_review(
        self, app_client: Any, journey: dict[str, Any]
    ) -> None:
        record = app_client.get(
            f"/api/v1/intakes/{journey['intake_id']}", headers=STAFF_HEADERS
        ).json()
        assert record["needs_review"] is True

    def test_the_intake_shows_on_the_worklist_needing_a_human(
        self, app_client: Any, journey: dict[str, Any]
    ) -> None:
        worklist = app_client.get("/api/v1/worklist", headers=STAFF_HEADERS).json()
        row = next(
            entry
            for entry in worklist["entries"]
            if entry["intake_id"] == journey["intake_id"]
        )
        assert row["state"] == "needs_review"
        assert row["contradiction_count"] >= 1


class TestTheReport:
    def test_it_renders_in_the_patients_language_by_default(
        self, app_client: Any, journey: dict[str, Any], content: Any
    ) -> None:
        """The intake was conducted in Hindi, so the report comes out in Hindi.

        Not the server's default and not the reader's preference: the language
        the patient answered in is the language their words are printed in, and
        a report that defaulted to English would put a translation beside them.
        """
        response = app_client.get(
            f"/api/v1/intakes/{journey['intake_id']}/report", headers=STAFF_HEADERS
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["language"] == "hi"
        assert content.templates.require("hi").text("header_disclaimer") in body["text"]

    @pytest.mark.parametrize("language", ["en", "hi"])
    def test_it_carries_the_disclaimer_the_conflict_and_the_raw_reading(
        self, app_client: Any, journey: dict[str, Any], content: Any, language: str
    ) -> None:
        response = app_client.get(
            f"/api/v1/intakes/{journey['intake_id']}/report",
            params={"language": language},
            headers=STAFF_HEADERS,
        )
        assert response.status_code == 200, response.text
        text = response.json()["text"]

        templates = content.templates.require(language)
        assert templates.text("header_disclaimer") in text
        assert templates.text("footer_disclaimer") in text
        # The patient's own words, in the script they were spoken in, in both.
        assert "पेट में दर्द" in text
        # The disputed dose, and the marker that says not to trust the digits.
        assert "900.2" in text
        assert templates.text("verify_marker") in text

    def test_it_states_no_diagnosis_and_no_advice(
        self, app_client: Any, journey: dict[str, Any]
    ) -> None:
        from app.domain.report.safety import find_unsupported_assertions

        text = app_client.get(
            f"/api/v1/intakes/{journey['intake_id']}/report", headers=STAFF_HEADERS
        ).json()["text"]
        assert find_unsupported_assertions(text) == ()

    def test_a_physician_can_verify_it(
        self, app_client: Any, journey: dict[str, Any]
    ) -> None:
        """Sign-off writes revisions; it does not edit the originals."""
        response = app_client.post(
            f"/api/v1/intakes/{journey['intake_id']}/verify",
            json={},
            headers=PHYSICIAN_HEADERS,
        )
        assert response.status_code == 200, response.text

        record = app_client.get(
            f"/api/v1/intakes/{journey['intake_id']}", headers=STAFF_HEADERS
        ).json()
        verified = [f for f in record["facts"] if f["physician_verified"]]
        assert verified, "verification recorded nothing"
        # An unsettled field never acquires a signature: that would be a
        # certainty increase with a physician's name attached to it.
        assert all(f["status"] == "answered" for f in verified)


class TestTheFHIRBundle:
    """§10 — the bundle, checked structurally.

    Not a schema validation: that runs against the public validator and is
    marked `network` in `tests/adapters/test_fhir.py`. What is asserted here is
    that the exchange format comes out of the *live pipeline* intact — with the
    documents and the contradictions in it, over HTTP, under a real token.
    """

    @pytest.fixture
    def bundle(self, app_client: Any, journey: dict[str, Any]) -> dict[str, Any]:
        response = app_client.get(
            f"/api/v1/fhir/intakes/{journey['intake_id']}", headers=STAFF_HEADERS
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/fhir+json")
        parsed: dict[str, Any] = response.json()
        return parsed

    def test_it_is_a_bundle_of_resolvable_resources(
        self, bundle: dict[str, Any]
    ) -> None:
        from tests.integration.fhir_checks import structural_errors

        assert structural_errors(bundle) == []

    def test_it_carries_the_patient_the_encounter_and_the_document(
        self, bundle: dict[str, Any]
    ) -> None:
        kinds = [entry["resource"]["resourceType"] for entry in bundle["entry"]]
        assert kinds[:2] == ["Patient", "Encounter"]
        assert "DocumentReference" in kinds
        assert "MedicationStatement" in kinds

    def test_the_unresolved_field_is_absent_rather_than_false(
        self, bundle: dict[str, Any]
    ) -> None:
        """Severity was asked and never settled.

        It must come out as `dataAbsentReason: unknown` — not as a value, and
        emphatically not as `false`. FHIR has the code because the distinction
        matters, and this is the one place a bundle could quietly lie.
        """
        severity = _resource_for_field(bundle, "Severity")
        assert "valueQuantity" not in severity
        assert severity["dataAbsentReason"]["coding"][0]["code"] == "unknown"

    def test_the_refused_field_says_it_was_refused(
        self, bundle: dict[str, Any]
    ) -> None:
        tobacco = _resource_for_field(bundle, "tobacco")
        assert tobacco["dataAbsentReason"]["coding"][0]["code"] == "asked-declined"

    def test_nothing_the_patient_said_was_translated(
        self, bundle: dict[str, Any]
    ) -> None:
        """`original_text` travels with the fact, in the original script."""
        originals = [
            extension["valueString"]
            for entry in bundle["entry"]
            for extension in entry["resource"].get("extension", [])
            if extension["url"].endswith("/original-text")
        ]
        assert "पेट में दर्द" in originals


def _resource_for_field(bundle: dict[str, Any], label: str) -> dict[str, Any]:
    """The resource whose `code.text` is `label`."""
    for entry in bundle["entry"]:
        resource = entry["resource"]
        if resource.get("code", {}).get("text") == label:
            return resource
    raise AssertionError(
        f"no resource for {label!r}; bundle has "
        f"{sorted({e['resource'].get('code', {}).get('text', '') for e in bundle['entry']})}"
    )
