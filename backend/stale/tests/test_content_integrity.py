"""The clinical content itself must be sound.

These checks fail the build rather than degrading at runtime. A red-flag rule
that reads a concept nobody asks can never fire, and a system that silently asks
fewer safety questions than it was configured to is exactly the failure mode
worth refusing to boot over.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.content import ClinicalContent, load_clinical_content
from app.core.errors import ContentError
from app.domain.clinical.enums import SECTION_ORDER, Section
from app.domain.ontology.pathway import PathwayRegistry
from app.domain.summary.templates import find_prompt_violations

REQUIRED_PATHWAYS = {
    "abdominal_pain",
    "chest_pain",
    "fever",
    "headache",
    "joint_pain",
    "general_follow_up",
}


class TestShippedContent:
    def test_the_brief_s_required_pathways_all_ship(self, content: ClinicalContent) -> None:
        assert set(content.pathways.ids()) >= REQUIRED_PATHWAYS

    def test_every_pathway_has_at_least_one_required_field(
        self, content: ClinicalContent
    ) -> None:
        for pathway in content.pathways:
            assert pathway.required_fields, pathway.pathway_id

    def test_the_fallback_pathway_exists_and_asks_real_questions(
        self, content: ClinicalContent
    ) -> None:
        """An unmatched complaint still deserves a structured history rather
        than a free-text box."""
        fallback = content.pathways.require(PathwayRegistry.FALLBACK_ID)
        assert len(fallback.required_fields) >= 4

    def test_every_pathway_field_references_a_known_concept(
        self, content: ClinicalContent
    ) -> None:
        for pathway in content.pathways:
            for field in pathway.fields:
                assert field.concept in content.concepts, (
                    f"{pathway.pathway_id}.{field.concept}"
                )

    def test_every_field_has_an_english_prompt_or_a_generated_fallback(
        self, content: ClinicalContent
    ) -> None:
        """There is always a question. A field that renders an empty string
        would show a patient a blank screen."""
        for pathway in content.pathways:
            for field in pathway.fields:
                assert field.prompt_for("en").strip()
                assert field.prompt_for(None).strip()

    def test_hindi_prompts_exist_for_every_core_and_pathway_field(
        self, content: ClinicalContent
    ) -> None:
        """An AYUSH OPD in Delhi is a Hindi-speaking room. A field that silently
        falls back to English is a field patients will not answer."""
        missing = [
            f"{pathway.pathway_id}.{field.concept}"
            for pathway in (content.content_set.core, *content.pathways)
            for field in pathway.fields
            if "hi" not in field.prompts
        ]
        assert missing == []

    def test_pathway_sections_are_in_the_known_section_set(
        self, content: ClinicalContent
    ) -> None:
        for pathway in content.pathways:
            for field in pathway.fields:
                assert field.section in SECTION_ORDER

    def test_the_core_intake_covers_every_mandatory_section(
        self, content: ClinicalContent
    ) -> None:
        sections = {f.section for f in content.content_set.core.fields}
        for required in (
            Section.IDENTITY,
            Section.CONSENT,
            Section.CHIEF_COMPLAINT,
            Section.PAST_MEDICAL,
            Section.PAST_SURGICAL,
            Section.MEDICATIONS,
            Section.ALLERGIES,
            Section.FAMILY_HISTORY,
            Section.PERSONAL_HISTORY,
            Section.DOCUMENTS,
            Section.CONFIRMATION,
        ):
            assert required in sections, required


class TestRedFlagScreenCoverage:
    def test_every_rule_concept_is_asked_by_some_screen_or_pathway(
        self, content: ClinicalContent
    ) -> None:
        """A rule reading a concept nobody asks can never fire. A silent
        never-firing safety rule is worse than no rule at all."""
        assert content.unscreened_rule_concepts() == ()

    def test_every_complaint_pathway_has_a_red_flag_screen(
        self, content: ClinicalContent
    ) -> None:
        screens = set(content.content_set.red_flag_screens.ids())
        for pathway_id in content.pathways.ids():
            if pathway_id in {"core_intake", "general_follow_up"}:
                continue
            assert pathway_id in screens, pathway_id

    def test_the_default_screen_exists_for_unmatched_complaints(
        self, content: ClinicalContent
    ) -> None:
        assert content.content_set.red_flag_screens.get("general") is not None

    def test_screen_fields_that_gate_critical_rules_are_not_skippable(
        self, content: ClinicalContent
    ) -> None:
        """A patient may decline a history question. They should not be able to
        swipe past "are you struggling to breathe?" by accident."""
        for screen in content.content_set.red_flag_screens:
            unskippable = [f.concept for f in screen.fields if not f.skippable]
            assert unskippable, screen.pathway_id


class TestNoDiagnosticLanguage:
    """Invariant 1: MediKiosk is not a diagnostic system."""

    def test_no_prompt_gives_advice_or_offers_an_interpretation(
        self, content: ClinicalContent
    ) -> None:
        """A question may name a disease — that is how a past medical history is
        taken. It may never advise, and it may never interpret."""
        offenders: list[str] = []
        for pathway in (
            content.content_set.core,
            *content.pathways,
            *content.content_set.red_flag_screens,
            *content.content_set.review_of_systems,
        ):
            for field in pathway.fields:
                for language, text in field.prompts.items():
                    hits = find_prompt_violations(text)
                    if hits:
                        offenders.append(
                            f"{pathway.pathway_id}.{field.concept}[{language}]: {hits}"
                        )
        assert offenders == []

    def test_the_consent_notice_says_the_system_does_not_diagnose(
        self, content: ClinicalContent
    ) -> None:
        notice = content.consent["notice"]["en"].lower()
        assert "does not diagnose" in notice
        assert "does not give medical advice" in notice

    def test_the_consent_notice_says_refusing_costs_the_patient_nothing(
        self, content: ClinicalContent
    ) -> None:
        """A consent a patient feels pressured into is not consent."""
        notice = content.consent["notice"]["en"].lower()
        assert "does not affect your place in the queue" in notice


class TestConsentArtefact:
    def test_raw_audio_retention_is_a_separate_optional_purpose(
        self, content: ClinicalContent
    ) -> None:
        """Recording a patient's voice and keeping it are different asks."""
        purposes = {p["code"]: p for p in content.consent["purposes"]}
        audio = purposes["raw_audio_retention"]
        assert audio["required"] is False
        assert audio.get("default_granted", False) is False

    def test_the_base_intake_purpose_is_required(self, content: ClinicalContent) -> None:
        purposes = {p["code"]: p for p in content.consent["purposes"]}
        assert purposes["history_intake"]["required"] is True

    def test_every_purpose_is_described_in_hindi_as_well_as_english(
        self, content: ClinicalContent
    ) -> None:
        for purpose in content.consent["purposes"]:
            assert "hi" in purpose["label"]
            assert "hi" in purpose["description"]

    def test_a_withdrawal_route_is_documented(self, content: ClinicalContent) -> None:
        assert content.consent["withdrawal"]["en"]


class TestLoaderStrictness:
    def test_a_missing_content_directory_is_fatal(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(ContentError, match="not found"):
            load_clinical_content(
                Settings(environment="test", clinical_content_dir=tmp_path / "absent")
            )

    def test_an_unparseable_rule_raises_rather_than_being_skipped(self) -> None:
        from app.domain.redflags.rules import RedFlagError, RedFlagRule

        with pytest.raises(RedFlagError):
            RedFlagRule.from_mapping(
                {
                    "id": "bad",
                    "clinical_source": "test",
                    "criteria": {"concept": "fever", "status": "definitely"},
                }
            )

    def test_an_unknown_expression_key_is_rejected(self) -> None:
        """A misspelt `critera:` must not silently disable a safety rule."""
        from app.domain.ontology.expressions import ExpressionError, parse_expression

        with pytest.raises(ExpressionError, match="unknown expression keys"):
            parse_expression({"concept": "fever", "statuss": "present"})


class TestClinicalReviewQueue:
    def test_items_needing_clinician_review_are_enumerated(
        self, content: ClinicalContent
    ) -> None:
        """`docs/CLINICAL_REVIEW_QUEUE.md` is generated from this, and it is the
        agenda for the AIIA mentor session."""
        queue = content.review_queue()
        assert queue
        assert any("abdominal_rigidity" in item for item in queue)
        assert any("thunderclap" in item.lower() for item in queue)
