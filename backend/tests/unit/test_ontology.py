"""Concept registry, criteria expressions, pathway parsing and terminology matching."""

from __future__ import annotations

import pytest

from app.domain.clinical.enums import AnswerShape, FactStatus, Section
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.clinical.provenance import (
    CodedValue,
    Duration,
    IntakeId,
    Quantity,
    ScaleValue,
    TextValue,
)
from app.domain.ontology.concepts import (
    Concept,
    ConceptRegistry,
    normalise_token,
)
from app.domain.ontology.expressions import (
    ExpressionError,
    parse_expression,
)
from app.domain.ontology.matching import (
    Candidate,
    fold,
    score_candidate,
    search,
    similarity,
    transliterate,
    trigrams,
)
from app.domain.ontology.pathway import (
    AnswerSpec,
    Pathway,
    PathwayError,
    PathwayField,
    PathwayRegistry,
)
from tests.conftest import make_fact


def state_with(*facts: tuple[str, FactStatus, object]) -> PatientIntakeState:
    state = PatientIntakeState(intake_id=IntakeId("i"))
    for index, (concept, status, value) in enumerate(facts):
        state = state.apply(
            make_fact(concept, status=status, value=value, fact_id=f"f{index}")
        )
    return state


class TestConceptRegistry:
    @pytest.fixture
    def registry(self) -> ConceptRegistry:
        return ConceptRegistry.from_mapping(
            {
                "chest_pain": {
                    "display": "Chest pain",
                    "section": "chief_complaint",
                    "synonyms": ["seene mein dard", "सीने में दर्द"],
                    "codes": {"NAMASTE": "AY-HRD-SHL", "ICD11-MMS": "MD30"},
                },
                "cough": {
                    "display": "Cough",
                    "section": "hpi",
                    "ros_group": "respiratory",
                    "needs_clinical_review": True,
                },
            }
        )

    def test_a_synonym_resolves_to_the_concept(self, registry: ConceptRegistry) -> None:
        assert registry.resolve("seene mein dard").concept_id == "chest_pain"
        assert registry.resolve("सीने में दर्द").concept_id == "chest_pain"

    def test_resolution_is_case_and_punctuation_insensitive(
        self, registry: ConceptRegistry
    ) -> None:
        assert registry.resolve("Seene, mein  DARD!").concept_id == "chest_pain"

    def test_an_unknown_expression_resolves_to_nothing_rather_than_a_guess(
        self, registry: ConceptRegistry
    ) -> None:
        assert registry.resolve("something nobody said") is None

    def test_a_ref_carries_a_code_only_for_a_system_that_has_one(
        self, registry: ConceptRegistry
    ) -> None:
        """An absent code is correct; an invented one is a defect."""
        concept = registry.require("chest_pain")
        assert concept.ref("NAMASTE").code == "AY-HRD-SHL"
        assert concept.ref("ICD11-TM2").code is None

    def test_an_unregistered_concept_still_produces_a_usable_ref(
        self, registry: ConceptRegistry
    ) -> None:
        """An extraction naming a concept we do not yet model must not be lost."""
        assert registry.ref("brand_new_concept").concept_id == "brand_new_concept"

    def test_lookups_by_section_and_ros_group(self, registry: ConceptRegistry) -> None:
        assert {c.concept_id for c in registry.in_section(Section.HPI)} == {"cough"}
        assert {c.concept_id for c in registry.in_ros_group("respiratory")} == {"cough"}

    def test_concepts_needing_review_are_enumerated(self, registry: ConceptRegistry) -> None:
        assert {c.concept_id for c in registry.needing_review()} == {"cough"}

    def test_duplicate_concept_ids_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate concept id"):
            ConceptRegistry(
                [
                    Concept("x", "X", Section.HPI),
                    Concept("x", "X again", Section.HPI),
                ]
            )

    def test_a_concept_without_a_section_fails_to_load(self) -> None:
        with pytest.raises(ValueError, match="missing 'section'"):
            Concept.from_mapping("x", {"display": "X"})

    def test_require_raises_on_an_unknown_concept(self, registry: ConceptRegistry) -> None:
        with pytest.raises(KeyError, match="unknown concept"):
            registry.require("nope")

    def test_membership_and_length(self, registry: ConceptRegistry) -> None:
        assert "cough" in registry
        assert len(registry) == 2
        assert {c.concept_id for c in registry} == {"chest_pain", "cough"}

    def test_normalise_preserves_devanagari(self) -> None:
        assert normalise_token("सीने  में, दर्द") == "सीने में दर्द"


class TestExpressions:
    def test_a_status_leaf(self) -> None:
        expr = parse_expression({"concept": "fever", "status": "present"})
        assert expr.evaluate(state_with(("fever", FactStatus.PRESENT, None)))
        assert not expr.evaluate(state_with(("fever", FactStatus.ABSENT, None)))

    def test_an_unestablished_concept_makes_a_leaf_false_rather_than_raising(self) -> None:
        """A rule that cannot be evaluated has not fired."""
        expr = parse_expression({"concept": "fever", "status": "present"})
        assert not expr.evaluate(PatientIntakeState(intake_id=IntakeId("i")))

    def test_in_matches_a_coded_value(self) -> None:
        expr = parse_expression({"concept": "onset", "in": ["sudden"]})
        assert expr.evaluate(state_with(("onset", FactStatus.PRESENT, CodedValue(code="sudden"))))
        assert not expr.evaluate(
            state_with(("onset", FactStatus.PRESENT, CodedValue(code="gradual")))
        )

    def test_not_in_excludes(self) -> None:
        expr = parse_expression({"concept": "onset", "not_in": ["gradual"]})
        assert expr.evaluate(state_with(("onset", FactStatus.PRESENT, CodedValue(code="sudden"))))

    def test_in_matches_free_text(self) -> None:
        expr = parse_expression({"concept": "note", "in": ["metformin"]})
        assert expr.evaluate(state_with(("note", FactStatus.PRESENT, TextValue("metformin"))))

    def test_numeric_comparison_on_a_scale(self) -> None:
        expr = parse_expression({"concept": "severity", "gte": 7})
        assert expr.evaluate(
            state_with(("severity", FactStatus.PRESENT, ScaleValue(8, 0, 10)))
        )
        assert not expr.evaluate(
            state_with(("severity", FactStatus.PRESENT, ScaleValue(6, 0, 10)))
        )

    def test_numeric_comparison_on_a_quantity_and_a_duration(self) -> None:
        assert parse_expression({"concept": "age", "gte": 60}).evaluate(
            state_with(("age", FactStatus.PRESENT, Quantity(72, "years")))
        )
        assert parse_expression({"concept": "duration", "lt": 5}).evaluate(
            state_with(("duration", FactStatus.PRESENT, Duration(3, "days")))
        )

    def test_all_operators_on_a_leaf_must_hold_together(self) -> None:
        expr = parse_expression({"concept": "severity", "gte": 4, "lte": 8})
        assert expr.evaluate(state_with(("severity", FactStatus.PRESENT, ScaleValue(6, 0, 10))))
        assert not expr.evaluate(state_with(("severity", FactStatus.PRESENT, ScaleValue(9, 0, 10))))

    def test_a_value_operator_implies_the_concept_is_present(self) -> None:
        """"severity >= 7" implicitly means the severity was actually reported."""
        expr = parse_expression({"concept": "severity", "gte": 7})
        assert not expr.evaluate(state_with(("severity", FactStatus.UNKNOWN, None)))

    def test_a_valueless_fact_fails_a_value_operator(self) -> None:
        expr = parse_expression({"concept": "severity", "gte": 7})
        assert not expr.evaluate(state_with(("severity", FactStatus.PRESENT, None)))

    def test_answered_leaf(self) -> None:
        expr = parse_expression({"concept": "fever", "answered": True})
        assert expr.evaluate(state_with(("fever", FactStatus.UNKNOWN, None)))
        assert not expr.evaluate(PatientIntakeState(intake_id=IntakeId("i")))

    def test_all_any_and_none(self) -> None:
        state = state_with(
            ("fever", FactStatus.PRESENT, None), ("cough", FactStatus.ABSENT, None)
        )
        assert parse_expression(
            {"all": [{"concept": "fever", "status": "present"}, {"concept": "cough", "status": "absent"}]}
        ).evaluate(state)
        assert parse_expression(
            {"any": [{"concept": "cough", "status": "present"}, {"concept": "fever", "status": "present"}]}
        ).evaluate(state)
        assert parse_expression({"none": [{"concept": "cough", "status": "present"}]}).evaluate(state)
        assert parse_expression({"not": {"concept": "cough", "status": "present"}}).evaluate(state)

    def test_concepts_are_reported_for_screen_coverage_checking(self) -> None:
        expr = parse_expression(
            {"all": [{"concept": "fever"}, {"any": [{"concept": "cough"}, {"concept": "rash"}]}]}
        )
        assert expr.concepts() == {"fever", "cough", "rash"}

    def test_describe_is_human_readable(self) -> None:
        """The description ends up on the alert, so triage can see the basis."""
        described = parse_expression(
            {"all": [{"concept": "fever", "status": "present"}, {"concept": "severity", "gte": 7}]}
        ).describe()
        assert "fever is present" in described
        assert "AND" in described
        assert "≥ 7" in described

    @pytest.mark.parametrize(
        ("raw", "message"),
        [
            ({"statuss": "present", "concept": "x"}, "unknown expression keys"),
            ({"status": "present"}, "requires 'concept'"),
            ({"concept": "x", "status": "maybe"}, "unknown status"),
            ({"concept": "x", "in": "sudden"}, "must be a list"),
            ({"concept": "x", "gte": "seven"}, "must be a number"),
            ({"all": []}, "must not be empty"),
            ({"all": [], "any": []}, "exactly one key"),
            ({"all": {"concept": "x"}}, "takes a list"),
            ({"not": ["x"]}, "single expression"),
        ],
    )
    def test_malformed_expressions_are_rejected_at_load_time(
        self, raw: dict, message: str
    ) -> None:
        """A rule that does not parse must fail the build, not fail silently at
        runtime."""
        with pytest.raises(ExpressionError, match=message):
            parse_expression(raw)


class TestPathwayParsing:
    def test_a_minimal_pathway_parses(self) -> None:
        pathway = Pathway.from_mapping(
            {
                "id": "p1",
                "version": 2,
                "matches_concepts": ["x"],
                "review_of_systems": ["gi"],
                "fields": [{"concept": "onset", "answer": {"type": "single_choice", "options": ["a"]}}],
            }
        )
        assert pathway.version == 2
        assert pathway.matches("x")
        assert pathway.review_of_systems == ("gi",)
        assert pathway.field_for("onset") is not None
        assert pathway.fields_in(Section.HPI)

    def test_a_pathway_without_an_id_is_rejected(self) -> None:
        with pytest.raises(PathwayError, match="requires 'id'"):
            Pathway.from_mapping({"fields": []})

    def test_a_repeated_concept_is_rejected(self) -> None:
        """Asking a patient the same question twice in one pathway is a content
        bug, and it must be caught in review rather than in the waiting room."""
        with pytest.raises(PathwayError, match="repeats concept"):
            Pathway.from_mapping(
                {"id": "p", "fields": [{"concept": "onset"}, {"concept": "onset"}]}
            )

    def test_a_field_without_a_concept_is_rejected(self) -> None:
        with pytest.raises(PathwayError, match="requires 'concept'"):
            Pathway.from_mapping({"id": "p", "fields": [{"required": True}]})

    def test_a_choice_answer_without_options_is_rejected(self) -> None:
        with pytest.raises(PathwayError, match="requires 'options'"):
            AnswerSpec.from_mapping({"type": "single_choice"})

    def test_a_scale_without_bounds_is_rejected(self) -> None:
        with pytest.raises(PathwayError, match="requires 'min' and 'max'"):
            AnswerSpec.from_mapping({"type": "scale"})

    def test_an_unknown_answer_type_is_rejected(self) -> None:
        with pytest.raises(PathwayError, match="unknown answer type"):
            AnswerSpec.from_mapping({"type": "telepathy"})

    def test_a_missing_answer_block_defaults_to_free_text(self) -> None:
        assert AnswerSpec.from_mapping(None).shape is AnswerShape.FREE_TEXT

    def test_non_list_fields_and_prompts_are_rejected(self) -> None:
        with pytest.raises(PathwayError, match="'fields' must be a list"):
            Pathway.from_mapping({"id": "p", "fields": "onset"})
        with pytest.raises(PathwayError, match="'prompts' must be a mapping"):
            PathwayField.from_mapping(
                {"concept": "x", "prompts": ["hello"]}, default_section=Section.HPI
            )

    def test_prompt_falls_back_from_a_regional_tag_to_the_base_language(self) -> None:
        field = PathwayField.from_mapping(
            {"concept": "x", "prompts": {"hi": "प्रश्न"}}, default_section=Section.HPI
        )
        assert field.prompt_for("hi-IN") == "प्रश्न"

    def test_prompt_falls_back_to_english_then_to_a_generated_phrasing(self) -> None:
        english = PathwayField.from_mapping(
            {"concept": "x", "prompts": {"en": "Question?"}}, default_section=Section.HPI
        )
        assert english.prompt_for("ta") == "Question?"
        bare = PathwayField.from_mapping({"concept": "joint_pain"}, default_section=Section.HPI)
        assert "joint pain" in bare.prompt_for("en")


class TestPathwayRegistry:
    @pytest.fixture
    def registry(self) -> PathwayRegistry:
        return PathwayRegistry.from_mappings(
            [
                {"id": "fever", "matches_concepts": ["jwara"], "fields": [{"concept": "onset"}]},
                {
                    "id": PathwayRegistry.FALLBACK_ID,
                    "fields": [{"concept": "duration"}],
                },
            ]
        )

    def test_match_by_id_and_by_synonym(self, registry: PathwayRegistry) -> None:
        assert registry.match("fever").pathway_id == "fever"
        assert registry.match("jwara").pathway_id == "fever"

    def test_no_match_returns_none_and_the_fallback_is_explicit(
        self, registry: PathwayRegistry
    ) -> None:
        assert registry.match("unmapped") is None
        assert registry.match_or_fallback("unmapped").pathway_id == PathwayRegistry.FALLBACK_ID

    def test_duplicate_pathway_ids_are_rejected(self) -> None:
        with pytest.raises(PathwayError, match="duplicate pathway id"):
            PathwayRegistry.from_mappings([{"id": "a", "fields": []}, {"id": "a", "fields": []}])

    def test_require_raises_on_an_unknown_pathway(self, registry: PathwayRegistry) -> None:
        with pytest.raises(KeyError, match="unknown pathway"):
            registry.require("nope")

    def test_fields_needing_review_are_enumerated(self) -> None:
        registry = PathwayRegistry.from_mappings(
            [{"id": "a", "fields": [{"concept": "x", "needs_clinical_review": True}]}]
        )
        assert [pid for pid, _ in registry.fields_needing_review()] == ["a"]

    def test_length_and_iteration(self, registry: PathwayRegistry) -> None:
        assert len(registry) == 2
        assert {p.pathway_id for p in registry} == set(registry.ids())


class TestTerminologyMatching:
    def test_devanagari_transliterates_to_latin(self) -> None:
        assert "sandhigat" in transliterate("संधिगत").replace(" ", "")

    def test_spelling_variants_fold_together(self) -> None:
        """"shula", "sula" and "shoola" are the same word spelled three ways."""
        assert fold("Shula") == fold("Sula")
        assert fold("vaata") == fold("vata")

    def test_an_exact_folded_match_scores_one(self) -> None:
        assert similarity("Jwara", "jwara") == 1.0

    def test_a_near_miss_scores_between_zero_and_one(self) -> None:
        score = similarity("sandhigat vaat", "Sandhigata Vata")
        assert 0.0 < score < 1.0

    def test_unrelated_terms_score_zero(self) -> None:
        assert similarity("jwara", "xyz") == 0.0

    def test_an_empty_query_scores_zero(self) -> None:
        assert similarity("", "jwara") == 0.0

    def test_trigrams_are_padded_so_prefixes_count(self) -> None:
        assert "__j" in trigrams("jwara")
        assert trigrams("") == frozenset()

    def test_search_ranks_best_first_and_filters_by_system(self) -> None:
        candidates = [
            Candidate("AY-JWR", "Jwara", "NAMASTE", ("ज्वर", "fever")),
            Candidate("MG26", "Fever of other or unknown origin", "ICD11-MMS"),
        ]
        results = search("jwara", candidates)
        assert results[0].code == "AY-JWR"
        assert search("jwara", candidates, systems=["ICD11-MMS"]) == ()

    def test_search_is_deterministic_under_ties(self) -> None:
        """Two runs of the same query must not return the same set in a
        different order, or the evaluation harness becomes flaky."""
        candidates = [
            Candidate("B", "Same", "ICD11-MMS"),
            Candidate("A", "Same", "ICD11-MMS"),
        ]
        assert [r.code for r in search("same", candidates)] == ["A", "B"]

    def test_a_candidate_reports_which_term_matched(self) -> None:
        candidate = Candidate("AY-JWR", "Jwara", "NAMASTE", ("bukhar",))
        assert score_candidate("bukhar", candidate).matched_on == "bukhar"

    def test_the_limit_is_respected(self) -> None:
        candidates = [Candidate(f"C{i}", "fever", "ICD11-MMS") for i in range(10)]
        assert len(search("fever", candidates, limit=3)) == 3
