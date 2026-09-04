"""Status vocabulary — §13.6.

`unresolved`, `not_asked`, `not_applicable` and `refused` must survive ingest →
storage → report **distinctly**, and none of them may render as `no`.

This is the test the whole record model exists to pass. Every other design
decision in `app/domain/record.py` — five statuses instead of a boolean, no
default on `FieldStatus`, a `denies()` that demands an explicit answered false —
is there so this cannot regress quietly.

Getting it wrong is not a cosmetic bug. "We never asked about breathlessness"
rendered as "denies breathlessness" is a false negative in a document a
physician acts on, and it looks exactly like a true one.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.domain.clinical.enums import Section
from app.domain.record import (
    VALUELESS_STATUSES,
    Boolean,
    Fact,
    FactChannel,
    FieldStatus,
    TurnSource,
)
from app.domain.report import builder
from tests.conftest import FROZEN_NOW, HOSPITAL_ID

UNSETTLED = (
    FieldStatus.UNRESOLVED,
    FieldStatus.NOT_ASKED,
    FieldStatus.NOT_APPLICABLE,
    FieldStatus.REFUSED,
)


def _fact(field_id: str, status: FieldStatus, value: Any = None) -> Fact:
    return Fact(
        fact_id=f"fact_{field_id}_{status.value}",
        field_id=field_id,
        status=status,
        value=value,
        source=TurnSource(turn_id=1),
        section=Section.RED_FLAG_SCREEN,
        channel=FactChannel.VOICE,
        recorded_at=FROZEN_NOW,
    )


class TestTheModelKeepsThemApart:
    def test_the_vocabulary_has_exactly_five_members(self) -> None:
        """A sixth member is a design change; a fifth removed is a regression."""
        assert {s.value for s in FieldStatus} == {
            "answered",
            "unresolved",
            "not_asked",
            "not_applicable",
            "refused",
        }

    @pytest.mark.parametrize("status", UNSETTLED)
    def test_unsettled_statuses_refuse_a_value(self, status: FieldStatus) -> None:
        """The model will not let an unsettled field carry an answer.

        This is the structural half of the guarantee: not "we are careful not to
        set a value", but "a value cannot be set".
        """
        assert status in VALUELESS_STATUSES
        with pytest.raises(ValueError, match="must not carry a value"):
            _fact("breathlessness", status, Boolean(value=False))

    @pytest.mark.parametrize("status", UNSETTLED)
    def test_no_unsettled_status_denies_anything(self, status: FieldStatus) -> None:
        """`denies()` is False for every status but an answered false.

        The single most important assertion in the suite. Every path that asks
        "did the patient say no" goes through this method, and it answers no to
        all four ways of not having said anything.
        """
        fact = _fact("breathlessness", status)
        assert fact.denies() is False
        assert fact.asserts() is False
        assert fact.is_answered is False
        assert fact.is_established is False

    def test_only_an_answered_false_denies(self) -> None:
        fact = _fact("breathlessness", FieldStatus.ANSWERED, Boolean(value=False))
        assert fact.denies() is True
        assert fact.asserts() is False

    def test_an_answered_true_does_not_deny(self) -> None:
        fact = _fact("breathlessness", FieldStatus.ANSWERED, Boolean(value=True))
        assert fact.denies() is False
        assert fact.asserts() is True

    def test_the_four_are_mutually_distinct(self) -> None:
        """No two unsettled statuses compare equal, at any layer."""
        assert len({s.value for s in UNSETTLED}) == 4


class TestTheyReachStorageIntact:
    async def test_round_trip_through_the_database(
        self, session: Any, ingest_service: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        """Ingest → storage → load preserves every status exactly."""
        from app.repositories.intakes import IntakeRepository

        result = await ingest_service.ingest(
            kiosk_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        loaded = await IntakeRepository(session).load(
            hospital_id=HOSPITAL_ID, intake_id=result.intake_id
        )
        by_field = {f.field_id: f for f in loaded.live_facts()}

        assert by_field["severity"].status is FieldStatus.UNRESOLVED
        assert by_field["breathlessness"].status is FieldStatus.NOT_ASKED
        assert by_field["pregnancy"].status is FieldStatus.NOT_APPLICABLE
        assert by_field["tobacco"].status is FieldStatus.REFUSED
        assert by_field["drug_allergy"].status is FieldStatus.ANSWERED

        # And the one that is genuinely a denial is the only one that denies.
        assert by_field["drug_allergy"].denies() is True
        for field_id in ("severity", "breathlessness", "pregnancy", "tobacco"):
            assert by_field[field_id].denies() is False
            assert by_field[field_id].value is None


class TestTheyRenderDistinctly:
    async def test_the_report_says_something_different_for_each(
        self, ingest_service: Any, report_service: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        """Four statuses, four sentences, none of them a denial."""
        result = await ingest_service.ingest(
            kiosk_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        bundle = await report_service.build(
            hospital_id=HOSPITAL_ID, intake_id=result.intake_id, language="en"
        )
        lines = {
            line.field_ids[0]: line.text for line in bundle.report.unresolved
        }

        assert "not established" in lines["severity"]
        assert "not established" in lines["breathlessness"]
        assert "declined to answer" in lines["tobacco"]
        assert "not applicable" in lines["pregnancy"]

        # Four fields, four distinct lines.
        assert len(set(lines.values())) == 4

        # Three distinct *phrasings* underneath. `unresolved` and `not_asked`
        # share one deliberately — the physician's next action is the same, ask
        # the question — and the machine-readable status stays on the structured
        # line for anything that needs to tell them apart. `refused` and
        # `not_applicable` each get their own, because both tell the physician
        # not to ask again, for opposite reasons.
        phrasings = {
            text.split("—", 1)[1].strip() for text in lines.values() if "—" in text
        }
        assert len(phrasings) == 3

    async def test_nothing_unsettled_renders_as_a_denial(
        self,
        content: Any,
        ingest_service: Any,
        report_service: Any,
        kiosk_payload: dict[str, Any],
    ) -> None:
        """The failing mode, stated directly.

        No unsettled field may render using the *denial* template, in either
        language. Checked against the template each language actually defines
        rather than against a keyword list, because "लागू नहीं" — not applicable
        — legitimately contains "नहीं", and a keyword test would either miss the
        real failure or forbid correct Hindi.
        """
        result = await ingest_service.ingest(
            kiosk_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        for language in ("en", "hi"):
            templates = content.templates.require(language)
            # The denial template with its placeholder removed: "Denies ",
            # "  से इनकार". Any unsettled line containing this fragment has been
            # rendered as a denial.
            denial_fragment = templates.text("denies").replace("{field}", "").strip()
            bundle = await report_service.build(
                hospital_id=HOSPITAL_ID, intake_id=result.intake_id, language=language
            )
            for line in bundle.report.unresolved:
                assert denial_fragment not in line.text, (
                    f"{language}: {line.field_ids} rendered with the denial template: "
                    f"{line.text!r}"
                )
                assert "absent" not in line.text.lower()
                assert not line.text.lower().endswith(": no")

    async def test_unsettled_fields_are_never_omitted(
        self, ingest_service: Any, report_service: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        """Every unsettled field appears somewhere on the report.

        Omission is the other way to lose the distinction: a field that is
        simply absent reads, to a physician skimming, exactly like a field that
        was asked and came back negative.
        """
        result = await ingest_service.ingest(
            kiosk_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        record = await report_service.load_record(
            hospital_id=HOSPITAL_ID, intake_id=result.intake_id
        )
        bundle = await report_service.build(
            hospital_id=HOSPITAL_ID, intake_id=result.intake_id, language="en"
        )
        rendered = {fid for line in bundle.report.unresolved for fid in line.field_ids}
        expected = {
            f.field_id for f in record.live_facts() if f.status is not FieldStatus.ANSWERED
        }
        assert expected <= rendered

    def test_the_builder_maps_each_status_to_its_own_template_key(
        self, content: Any
    ) -> None:
        """A direct check on the branch that does the rendering."""
        templates = content.templates.require("en")
        labels = builder.FieldLabels({})
        texts = {
            status: builder._unresolved_line(
                _fact("x", status), templates, labels
            ).text
            for status in UNSETTLED
        }
        assert texts[FieldStatus.REFUSED] != texts[FieldStatus.UNRESOLVED]
        assert texts[FieldStatus.NOT_APPLICABLE] != texts[FieldStatus.UNRESOLVED]
        assert all("denies" not in t.lower() for t in texts.values())
