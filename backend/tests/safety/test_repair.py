"""The repair path — §13.5.

Three claims:

1. A deliberately malformed payload goes through repair, produces a valid
   record, and **every repaired field is marked**.
2. A payload that cannot be repaired is **stored and flagged, never dropped**.
3. Repair never invents a value. A field with no answer comes back
   `unresolved`, not filled in.

The third is the one that matters. A repair step that quietly resolved
ambiguities would be a language model editing a clinical record, which is the
one thing §5.1 exists to prevent.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.adapters.llm.mock import MockRepairProvider
from app.services import repair as repair_path
from tests.conftest import HOSPITAL_ID


def malformed(**overrides: Any) -> dict[str, Any]:
    """A payload the 0.1 contract rejects.

    `severity` has no `status`, which the contract refuses on purpose: a field
    whose status nobody recorded has not told us whether it was asked, and
    guessing would be exactly the silent certainty increase hard rule 2 forbids.
    """
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "intake_id": "aa11bb22-0000-4000-8000-00000000dead",
        "hospital_id": HOSPITAL_ID,
        "status": "complete",
        "language": "hi",
        "reporter": "self",
        "turns": [{"turn_id": 1, "transcript": "पेट में दर्द", "asr_confidence": 0.9}],
        "fields": {
            "chief_complaint": {
                "value": "abdominal_pain",
                "status": "answered",
                "original_text": "पेट में दर्द",
                "source_turn": 1,
            },
            # No status. The contract rejects it; repair must mark it
            # unresolved, not answered.
            "severity": {"value": None},
            # A bare value, not wrapped. Repair may wrap it — the value is real.
            "duration": 3,
        },
    }
    payload.update(overrides)
    return payload


class TestTheHappyPathNeverCallsAModel:
    async def test_a_valid_payload_skips_repair(
        self, kiosk_payload: dict[str, Any]
    ) -> None:
        """Most payloads. No model call, and `repaired` stays false.

        This is what makes `repair_rate` a meaningful number: it counts the
        exceptions, not the traffic.
        """
        outcome = await repair_path.attempt(
            kiosk_payload, provider=_recording_provider()
        )
        assert outcome.reason == "ok"
        assert outcome.repaired is False
        assert outcome.payload is kiosk_payload


class TestRepairProducesAValidRecord:
    async def test_a_malformed_payload_is_repaired(self) -> None:
        outcome = await repair_path.attempt(
            malformed(), provider=MockRepairProvider()
        )
        assert outcome.reason == "repaired"
        assert outcome.repaired is True
        assert outcome.payload is not None
        ok, errors = repair_path.validate(outcome.payload)
        assert ok, errors

    async def test_repair_marks_only_the_fields_it_touched(self) -> None:
        """Over-marking makes the marker meaningless.

        A payload that failed on one entry should not demote the others — a
        physician who sees "verify" on every line stops reading it.
        """
        outcome = await repair_path.attempt(
            malformed(), provider=MockRepairProvider()
        )
        assert outcome.touched_fields == {"severity", "duration"}
        assert "chief_complaint" not in outcome.touched_fields

    async def test_a_field_with_no_answer_becomes_unresolved(self) -> None:
        """The central constraint. Repair restructures; it does not answer."""
        outcome = await repair_path.attempt(
            malformed(), provider=MockRepairProvider()
        )
        assert outcome.payload is not None
        assert outcome.payload["fields"]["severity"]["status"] == "unresolved"
        assert outcome.payload["fields"]["severity"]["value"] is None

    async def test_original_text_survives_repair(self) -> None:
        outcome = await repair_path.attempt(
            malformed(), provider=MockRepairProvider()
        )
        assert outcome.payload is not None
        assert (
            outcome.payload["fields"]["chief_complaint"]["original_text"]
            == "पेट में दर्द"
        )


class TestRepairedFactsAreMarked:
    async def test_every_repaired_fact_carries_the_flag(
        self, ingest_service: Any, session: Any
    ) -> None:
        from app.repositories.intakes import IntakeRepository

        result = await ingest_service.ingest(
            malformed(), hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        assert result.repaired is True
        assert result.needs_review is True

        record = await IntakeRepository(session).load(
            hospital_id=HOSPITAL_ID, intake_id=result.intake_id
        )
        assert record.provenance.repaired is True
        repaired = {f.field_id for f in record.live_facts() if f.repaired}
        assert repaired == {"severity", "duration"}

    async def test_a_repaired_fact_can_never_be_verified_at_ingest(
        self, ingest_service: Any, session: Any
    ) -> None:
        """The model invariant, checked end to end.

        `Fact` refuses the combination outright, so this is a check that nothing
        upstream tries to construct it.
        """
        from app.repositories.intakes import IntakeRepository

        result = await ingest_service.ingest(
            malformed(), hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        record = await IntakeRepository(session).load(
            hospital_id=HOSPITAL_ID, intake_id=result.intake_id
        )
        for fact in record.live_facts():
            if fact.repaired:
                assert fact.physician_verified is False

    async def test_a_repaired_field_renders_with_a_marker(
        self, ingest_service: Any, report_service: Any
    ) -> None:
        result = await ingest_service.ingest(
            malformed(), hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        bundle = await report_service.build(
            hospital_id=HOSPITAL_ID, intake_id=result.intake_id, language="en"
        )
        assert bundle.report.contains_repaired is True
        marked = [
            line
            for section in bundle.report.sections
            for line in section.lines
            if any(m.code == "repaired" for m in line.markers)
        ]
        assert marked, "a repaired fact rendered with no marker"
        assert "verify" in marked[0].rendered().lower()


class TestUnrepairableInputIsKept:
    async def test_a_payload_that_cannot_be_repaired_is_stored(
        self, session: Any, ingest_service: Any
    ) -> None:
        """**Never discard input.**

        Seven minutes of a patient's answers are worth more than a clean error
        response. The row keeps the payload whole so a human — or a normalizer
        that ships next week — can recover it.
        """
        from app.repositories.consent import IngestRawRepository

        # No `status`, which repair fills; but also an intake_id that is not a
        # string and a `fields` that is not a mapping, which it cannot.
        broken = {
            "schema_version": "0.1",
            "hospital_id": HOSPITAL_ID,
            "intake_id": "",
            "status": "complete",
            "fields": "not a mapping at all",
        }
        result = await ingest_service.ingest(
            broken, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        assert result.needs_manual_review is True
        assert result.status == "needs_manual_review"

        pending = await IngestRawRepository(session).pending(hospital_id=HOSPITAL_ID)
        assert len(pending) == 1
        assert pending[0].reason == "repair_failed"
        assert pending[0].payload["fields"] == "not a mapping at all"

    async def test_the_stored_errors_carry_no_clinical_text(
        self, session: Any, ingest_service: Any
    ) -> None:
        """Validation errors reach logs. Pydantic's `input` field does not.

        Pydantic attaches the offending value to every error, and for a clinical
        payload that value is the patient's own words. The payload itself is in
        the access-controlled `payload` column; the error list is not.
        """
        from app.repositories.consent import IngestRawRepository

        broken = {
            "schema_version": "0.1",
            "hospital_id": HOSPITAL_ID,
            "intake_id": "",
            "status": "complete",
            "fields": "पेट में बहुत तेज़ दर्द हो रहा है",
        }
        await ingest_service.ingest(broken, hospital_id=HOSPITAL_ID, actor_id="kiosk-1")
        pending = await IngestRawRepository(session).pending(hospital_id=HOSPITAL_ID)
        errors = str(pending[0].error_detail)
        assert "पेट" not in errors
        for error in pending[0].error_detail["errors"]:
            assert set(error) == {"loc", "type", "msg"}

    async def test_an_unsupported_version_is_stored_not_repaired(
        self, session: Any, ingest_service: Any
    ) -> None:
        """A device running ahead of the backend.

        Repair cannot help — there is no target schema to repair *to* — so the
        payload is kept whole and the normalizer ships later.
        """
        from app.repositories.consent import IngestRawRepository

        result = await ingest_service.ingest(
            {"schema_version": "0.9", "hospital_id": HOSPITAL_ID, "intake_id": "x"},
            hospital_id=HOSPITAL_ID,
            actor_id="kiosk-1",
        )
        assert result.needs_manual_review is True
        pending = await IngestRawRepository(session).pending(hospital_id=HOSPITAL_ID)
        assert pending[0].reason == "unsupported_version"
        assert pending[0].repair_attempted is False

    async def test_the_same_broken_payload_is_stored_once(
        self, session: Any, ingest_service: Any
    ) -> None:
        """A retrying kiosk does not fill the table.

        The payload fingerprint deduplicates, so a device that retries the same
        unparseable body produces one row for a human to look at, not four
        hundred.
        """
        from app.repositories.consent import IngestRawRepository

        broken = {
            "schema_version": "0.1",
            "hospital_id": HOSPITAL_ID,
            "intake_id": "",
            "status": "complete",
            "fields": "not a mapping",
        }
        for _ in range(3):
            await ingest_service.ingest(
                broken, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
            )
        pending = await IngestRawRepository(session).pending(hospital_id=HOSPITAL_ID)
        assert len(pending) == 1


class TestRepairCanBeSwitchedOff:
    async def test_no_provider_means_straight_to_manual_review(
        self, session: Any, bus: Any, clock: Any, ids: Any
    ) -> None:
        """`REPAIR_PROVIDER=none` is a supported configuration.

        A hospital that will not have a model touch patient input at all still
        gets ingest, documents and the report. Malformed payloads then go
        straight to `ingest_raw` — a worse outcome than repair, and an honest
        one.
        """
        from app.repositories.consent import AuditRepository, IngestRawRepository
        from app.repositories.intakes import IntakeRepository
        from app.services.ingest import IngestService

        service = IngestService(
            intakes=IntakeRepository(session),
            raw=IngestRawRepository(session),
            audit=AuditRepository(session),
            bus=bus,
            clock=clock,
            ids=ids,
            repair_provider=None,
        )
        result = await service.ingest(
            malformed(), hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        assert result.needs_manual_review is True
        pending = await IngestRawRepository(session).pending(hospital_id=HOSPITAL_ID)
        assert pending[0].reason == "repair_disabled"
        assert pending[0].repair_attempted is False


class TestTheRepairRateIsReported:
    async def test_the_counter_moves(
        self, session: Any, ingest_service: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        """`repair_rate` should fall as the extractor improves.

        A real quality metric, and a good number for the pitch — but only if it
        is actually computed, which is what this asserts.
        """
        from app.repositories.consent import MetricsRepository

        await ingest_service.ingest(
            kiosk_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        await ingest_service.ingest(
            malformed(), hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        metrics = await MetricsRepository(session).repair_rate(hospital_id=HOSPITAL_ID)
        assert metrics == {
            "intakes": 2,
            "repaired": 1,
            "needs_manual_review": 0,
            "repair_rate": 0.5,
        }


def _recording_provider() -> Any:
    """A provider that fails the test if it is ever called."""

    class _NeverCalled:
        name = "never-called"

        async def repair(self, payload: Any, *, schema: Any, errors: Any) -> Any:
            pytest.fail("the repair model was called for a payload that already validated")

    return _NeverCalled()
