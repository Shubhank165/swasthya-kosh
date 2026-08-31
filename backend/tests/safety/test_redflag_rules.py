"""Every shipped red-flag rule gets a positive and a negative test.

This file is the safety net for the clinical content. A rule that fires when it
should not costs a triage nurse thirty seconds; a rule that silently stops
firing because someone edited a concept id costs an emergency. The parametrised
cases below make the second failure loud.
"""

from __future__ import annotations

import pytest

from app.core.content import ClinicalContent
from app.domain.clinical.enums import FactStatus, Section, Severity
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.clinical.provenance import CodedValue, IntakeId, ScaleValue
from app.domain.redflags.evaluator import evaluate, evaluate_with_coverage
from app.domain.redflags.rules import SAFE_LABEL, label_is_safe
from tests.conftest import make_fact

#: (rule_id, facts that must fire it). Each entry is the clinical scenario the
#: rule exists to catch, written the way a patient would present it.
POSITIVE_CASES: list[tuple[str, list[tuple[str, FactStatus, object]]]] = [
    (
        "acute_chest_pain_with_dyspnoea",
        [
            ("chest_pain", FactStatus.PRESENT, None),
            ("onset", FactStatus.PRESENT, CodedValue(code="sudden")),
            ("dyspnoea", FactStatus.PRESENT, None),
        ],
    ),
    (
        "chest_pain_with_radiation",
        [
            ("chest_pain", FactStatus.PRESENT, None),
            ("radiation", FactStatus.PRESENT, CodedValue(code="to_left_arm")),
        ],
    ),
    (
        "chest_pain_with_syncope",
        [("chest_pain", FactStatus.PRESENT, None), ("syncope", FactStatus.PRESENT, None)],
    ),
    (
        "chest_pain_on_exertion_severe",
        [
            ("chest_pain", FactStatus.PRESENT, None),
            ("aggravating_factors", FactStatus.PRESENT, CodedValue(code="exertion")),
            ("severity", FactStatus.PRESENT, ScaleValue(8, 0, 10)),
        ],
    ),
    (
        "breathlessness_at_rest",
        [("dyspnoea", FactStatus.PRESENT, None), ("syncope", FactStatus.PRESENT, None)],
    ),
    ("gi_bleeding_suspected", [("haematemesis", FactStatus.PRESENT, None)]),
    (
        "acute_abdomen_with_rigidity",
        [
            ("abdominal_pain", FactStatus.PRESENT, None),
            ("abdominal_rigidity", FactStatus.PRESENT, None),
        ],
    ),
    (
        "severe_abdominal_pain_sudden_onset",
        [
            ("abdominal_pain", FactStatus.PRESENT, None),
            ("onset", FactStatus.PRESENT, CodedValue(code="sudden")),
            ("severity", FactStatus.PRESENT, ScaleValue(9, 0, 10)),
        ],
    ),
    (
        "abdominal_pain_with_persistent_vomiting",
        [
            ("abdominal_pain", FactStatus.PRESENT, None),
            ("associated_vomiting", FactStatus.PRESENT, None),
            ("reduced_urine_output", FactStatus.PRESENT, None),
        ],
    ),
    (
        "abdominal_pain_in_pregnancy",
        [("abdominal_pain", FactStatus.PRESENT, None), ("pregnancy", FactStatus.PRESENT, None)],
    ),
    (
        "fever_with_meningism",
        [("fever", FactStatus.PRESENT, None), ("neck_stiffness", FactStatus.PRESENT, None)],
    ),
    (
        "fever_with_bleeding",
        [
            ("fever", FactStatus.PRESENT, None),
            ("bleeding_manifestation", FactStatus.PRESENT, None),
        ],
    ),
    (
        "fever_with_reduced_urine_output",
        [("fever", FactStatus.PRESENT, None), ("reduced_urine_output", FactStatus.PRESENT, None)],
    ),
    (
        "prolonged_high_fever",
        [("fever", FactStatus.PRESENT, None), ("persistent_high_fever", FactStatus.PRESENT, None)],
    ),
    (
        "fever_with_breathlessness",
        [("fever", FactStatus.PRESENT, None), ("dyspnoea", FactStatus.PRESENT, None)],
    ),
    (
        "thunderclap_headache",
        [("headache", FactStatus.PRESENT, None), ("thunderclap_onset", FactStatus.PRESENT, None)],
    ),
    (
        "headache_with_focal_deficit",
        [("headache", FactStatus.PRESENT, None), ("focal_weakness", FactStatus.PRESENT, None)],
    ),
    (
        "headache_with_fever_and_neck_stiffness",
        [
            ("headache", FactStatus.PRESENT, None),
            ("associated_fever", FactStatus.PRESENT, None),
            ("neck_stiffness", FactStatus.PRESENT, None),
        ],
    ),
    ("focal_weakness_any_presentation", [("focal_weakness", FactStatus.PRESENT, None)]),
    (
        "septic_arthritis_screen",
        [
            ("joint_pain", FactStatus.PRESENT, None),
            ("joint_redness_warmth", FactStatus.PRESENT, None),
            ("associated_fever", FactStatus.PRESENT, None),
        ],
    ),
    ("altered_sensorium_any_presentation", [("altered_sensorium", FactStatus.PRESENT, None)]),
    ("syncope_any_presentation", [("syncope", FactStatus.PRESENT, None)]),
    ("unexplained_weight_loss", [("unintentional_weight_loss", FactStatus.PRESENT, None)]),
    (
        "anaphylaxis_history_with_new_prescription",
        [
            ("drug_allergy", FactStatus.PRESENT, None),
            (
                "allergy_reaction_type",
                FactStatus.PRESENT,
                CodedValue(code="breathing_difficulty"),
            ),
        ],
    ),
]

#: (rule_id, facts that must NOT fire it). Each is the near-miss the rule has to
#: stay quiet on — the one limb short, or the denial.
NEGATIVE_CASES: list[tuple[str, list[tuple[str, FactStatus, object]]]] = [
    (
        "acute_chest_pain_with_dyspnoea",
        [
            ("chest_pain", FactStatus.PRESENT, None),
            ("onset", FactStatus.PRESENT, CodedValue(code="gradual")),
            ("dyspnoea", FactStatus.ABSENT, None),
            ("diaphoresis", FactStatus.ABSENT, None),
        ],
    ),
    (
        "chest_pain_with_radiation",
        [
            ("chest_pain", FactStatus.PRESENT, None),
            ("radiation", FactStatus.PRESENT, CodedValue(code="none")),
        ],
    ),
    (
        "chest_pain_with_syncope",
        [("chest_pain", FactStatus.PRESENT, None), ("syncope", FactStatus.ABSENT, None)],
    ),
    (
        "chest_pain_on_exertion_severe",
        [
            ("chest_pain", FactStatus.PRESENT, None),
            ("aggravating_factors", FactStatus.PRESENT, CodedValue(code="exertion")),
            ("severity", FactStatus.PRESENT, ScaleValue(3, 0, 10)),
        ],
    ),
    (
        "breathlessness_at_rest",
        [("dyspnoea", FactStatus.PRESENT, None), ("syncope", FactStatus.ABSENT, None)],
    ),
    (
        "gi_bleeding_suspected",
        [("haematemesis", FactStatus.ABSENT, None), ("melaena", FactStatus.ABSENT, None)],
    ),
    (
        "acute_abdomen_with_rigidity",
        [
            ("abdominal_pain", FactStatus.PRESENT, None),
            ("abdominal_rigidity", FactStatus.ABSENT, None),
        ],
    ),
    (
        "severe_abdominal_pain_sudden_onset",
        [
            ("abdominal_pain", FactStatus.PRESENT, None),
            ("onset", FactStatus.PRESENT, CodedValue(code="gradual")),
            ("severity", FactStatus.PRESENT, ScaleValue(9, 0, 10)),
        ],
    ),
    (
        "abdominal_pain_with_persistent_vomiting",
        [
            ("abdominal_pain", FactStatus.PRESENT, None),
            ("associated_vomiting", FactStatus.PRESENT, None),
            ("reduced_urine_output", FactStatus.ABSENT, None),
        ],
    ),
    (
        "abdominal_pain_in_pregnancy",
        [
            ("abdominal_pain", FactStatus.PRESENT, None),
            ("pregnancy", FactStatus.NOT_APPLICABLE, None),
        ],
    ),
    (
        "fever_with_meningism",
        [
            ("fever", FactStatus.PRESENT, None),
            ("neck_stiffness", FactStatus.ABSENT, None),
            ("altered_sensorium", FactStatus.ABSENT, None),
        ],
    ),
    (
        "fever_with_bleeding",
        [("fever", FactStatus.PRESENT, None), ("bleeding_manifestation", FactStatus.ABSENT, None)],
    ),
    (
        "fever_with_reduced_urine_output",
        [("fever", FactStatus.PRESENT, None), ("reduced_urine_output", FactStatus.ABSENT, None)],
    ),
    (
        "prolonged_high_fever",
        [("fever", FactStatus.PRESENT, None), ("persistent_high_fever", FactStatus.ABSENT, None)],
    ),
    (
        "fever_with_breathlessness",
        [("fever", FactStatus.PRESENT, None), ("dyspnoea", FactStatus.ABSENT, None)],
    ),
    (
        "thunderclap_headache",
        [("headache", FactStatus.PRESENT, None), ("thunderclap_onset", FactStatus.ABSENT, None)],
    ),
    (
        "headache_with_focal_deficit",
        [
            ("headache", FactStatus.PRESENT, None),
            ("focal_weakness", FactStatus.ABSENT, None),
            ("altered_sensorium", FactStatus.ABSENT, None),
        ],
    ),
    (
        "headache_with_fever_and_neck_stiffness",
        [
            ("headache", FactStatus.PRESENT, None),
            ("associated_fever", FactStatus.PRESENT, None),
            ("neck_stiffness", FactStatus.ABSENT, None),
        ],
    ),
    ("focal_weakness_any_presentation", [("focal_weakness", FactStatus.ABSENT, None)]),
    (
        "septic_arthritis_screen",
        [
            ("joint_pain", FactStatus.PRESENT, None),
            ("joint_redness_warmth", FactStatus.ABSENT, None),
            ("associated_fever", FactStatus.PRESENT, None),
        ],
    ),
    ("altered_sensorium_any_presentation", [("altered_sensorium", FactStatus.ABSENT, None)]),
    ("syncope_any_presentation", [("syncope", FactStatus.ABSENT, None)]),
    ("unexplained_weight_loss", [("unintentional_weight_loss", FactStatus.ABSENT, None)]),
    (
        "anaphylaxis_history_with_new_prescription",
        [
            ("drug_allergy", FactStatus.PRESENT, None),
            ("allergy_reaction_type", FactStatus.PRESENT, CodedValue(code="rash")),
        ],
    ),
]


def build(facts: list[tuple[str, FactStatus, object]]) -> PatientIntakeState:
    state = PatientIntakeState(intake_id=IntakeId("i"))
    for index, (concept, status, value) in enumerate(facts):
        state = state.apply(
            make_fact(
                concept,
                status=status,
                value=value,
                fact_id=f"f{index}",
                section=Section.RED_FLAG_SCREEN,
            )
        )
    return state


@pytest.mark.parametrize(("rule_id", "facts"), POSITIVE_CASES, ids=[c[0] for c in POSITIVE_CASES])
def test_rule_fires_on_its_scenario(
    rule_id: str, facts: list[tuple[str, FactStatus, object]], content: ClinicalContent
) -> None:
    alerts = evaluate(build(facts), content.red_flags)
    assert rule_id in {a.rule_id for a in alerts}


@pytest.mark.parametrize(("rule_id", "facts"), NEGATIVE_CASES, ids=[c[0] for c in NEGATIVE_CASES])
def test_rule_stays_quiet_on_its_near_miss(
    rule_id: str, facts: list[tuple[str, FactStatus, object]], content: ClinicalContent
) -> None:
    alerts = evaluate(build(facts), content.red_flags)
    assert rule_id not in {a.rule_id for a in alerts}


def test_every_shipped_rule_has_both_a_positive_and_a_negative_case(
    content: ClinicalContent,
) -> None:
    """Definition of done item 6, enforced rather than remembered."""
    shipped = set(content.red_flags.ids())
    positives = {rule_id for rule_id, _ in POSITIVE_CASES}
    negatives = {rule_id for rule_id, _ in NEGATIVE_CASES}
    assert shipped - positives == set(), f"rules with no positive case: {shipped - positives}"
    assert shipped - negatives == set(), f"rules with no negative case: {shipped - negatives}"


class TestAlertWording:
    """Invariant 1 and 3: an alert never states a diagnosis."""

    def test_every_rule_uses_the_fixed_safe_label(self, content: ClinicalContent) -> None:
        for rule in content.red_flags:
            assert rule.label == SAFE_LABEL

    def test_no_rule_label_names_a_disease(self, content: ClinicalContent) -> None:
        for rule in content.red_flags:
            assert label_is_safe(rule.label), rule.rule_id

    def test_the_patient_safe_label_is_always_the_fixed_wording(
        self, content: ClinicalContent
    ) -> None:
        alerts = evaluate(build(POSITIVE_CASES[0][1]), content.red_flags)
        assert alerts
        for alert in alerts:
            assert alert.patient_safe_label == SAFE_LABEL

    def test_label_is_safe_rejects_a_diagnosis(self) -> None:
        assert not label_is_safe("Possible myocardial infarction")
        assert not label_is_safe("You have appendicitis")
        assert label_is_safe(SAFE_LABEL)


class TestRuleProvenance:
    def test_every_rule_names_who_approved_it(self, content: ClinicalContent) -> None:
        """"Who approved this rule?" is the first question any clinician asks."""
        for rule in content.red_flags:
            assert rule.clinical_source

    def test_a_rule_without_a_clinical_source_fails_to_load(self) -> None:
        from app.domain.redflags.rules import RedFlagError, RedFlagRule

        with pytest.raises(RedFlagError, match="clinical_source"):
            RedFlagRule.from_mapping(
                {"id": "x", "criteria": {"concept": "fever", "status": "present"}}
            )


class TestEvaluationProperties:
    def test_evaluation_is_deterministic(self, content: ClinicalContent) -> None:
        state = build(POSITIVE_CASES[0][1])
        assert [a.rule_id for a in evaluate(state, content.red_flags)] == [
            a.rule_id for a in evaluate(state, content.red_flags)
        ]

    def test_alerts_are_ordered_most_severe_first(self, content: ClinicalContent) -> None:
        state = build(
            [
                ("chest_pain", FactStatus.PRESENT, None),
                ("onset", FactStatus.PRESENT, CodedValue(code="sudden")),
                ("dyspnoea", FactStatus.PRESENT, None),
                ("unintentional_weight_loss", FactStatus.PRESENT, None),
            ]
        )
        alerts = evaluate(state, content.red_flags)
        assert alerts[0].severity is Severity.CRITICAL
        assert alerts[-1].severity is Severity.MODERATE

    def test_an_alert_carries_the_facts_that_fired_it(self, content: ClinicalContent) -> None:
        """Triage must be able to see the basis in one click rather than trust
        the alert."""
        state = build(POSITIVE_CASES[0][1])
        alert = next(
            a for a in evaluate(state, content.red_flags)
            if a.rule_id == "acute_chest_pain_with_dyspnoea"
        )
        assert alert.supporting_facts
        for fact_id in alert.supporting_facts:
            assert state.by_id(fact_id) is not None

    def test_an_unanswered_screen_never_fires_a_rule(self, content: ClinicalContent) -> None:
        """Silence is not a negative: a rule whose concepts were never asked
        must not fire, and the report must say the screen was incomplete."""
        empty = PatientIntakeState(intake_id=IntakeId("i"))
        report = evaluate_with_coverage(empty, content.red_flags)
        assert report.alerts == ()
        assert "dyspnoea" in report.unscreened_concepts

    def test_unknown_answers_do_not_fire_rules(self, content: ClinicalContent) -> None:
        state = build(
            [
                ("chest_pain", FactStatus.PRESENT, None),
                ("onset", FactStatus.UNKNOWN, None),
                ("dyspnoea", FactStatus.UNKNOWN, None),
            ]
        )
        assert "acute_chest_pain_with_dyspnoea" not in {
            a.rule_id for a in evaluate(state, content.red_flags)
        }
