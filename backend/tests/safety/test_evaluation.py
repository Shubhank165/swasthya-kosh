"""The evaluation harness runs in CI beside the unit tests.

Definition of done item 9: `python -m evaluation.run` prints the metrics table
and exits non-zero on any unsupported assertion. Running it here means a
regression in clinical safety fails the build like any other test rather than
waiting for someone to remember to run the harness.

The last two tests prove the harness is not vacuous — that it actually fails
when the system misbehaves. A green harness that cannot go red is worse than no
harness, because it is believed.
"""

from __future__ import annotations

import pytest

from app.core.content import ClinicalContent
from evaluation.harness import run_scenario, summarise
from evaluation.run import SCENARIO_DIR, main, run_all
from evaluation.scenario import Scenario, ScenarioError, load_scenarios

MINIMUM_SCENARIOS = 20


@pytest.fixture(scope="session")
def scenarios() -> tuple[Scenario, ...]:
    return load_scenarios(SCENARIO_DIR)


class TestCorpus:
    def test_the_corpus_meets_the_required_size(
        self, scenarios: tuple[Scenario, ...]
    ) -> None:
        assert len(scenarios) >= MINIMUM_SCENARIOS

    def test_every_pathway_is_exercised(
        self, scenarios: tuple[Scenario, ...], content: ClinicalContent
    ) -> None:
        """A pathway with no scenario is a pathway nobody has checked."""
        complaints = {
            str(turn.answer)
            for scenario in scenarios
            for turn in scenario.patient_script
            if turn.ask == "chief_complaint"
        }
        exercised = {
            content.pathways.match_or_fallback(complaint).pathway_id
            for complaint in complaints
        }
        expected = set(content.pathways.ids()) - {"core_intake"}
        assert expected <= exercised, f"pathways with no scenario: {expected - exercised}"

    def test_both_red_flag_directions_are_covered(
        self, scenarios: tuple[Scenario, ...]
    ) -> None:
        assert any(s.expect_red_flags for s in scenarios)
        assert any(s.forbid_red_flags for s in scenarios)

    def test_the_awkward_cases_are_covered(
        self, scenarios: tuple[Scenario, ...]
    ) -> None:
        """Contradiction, attendant-reported and abandonment — the three cases a
        happy-path corpus quietly omits."""
        ids = {s.scenario_id for s in scenarios}
        assert any(s.expect_contradictions for s in scenarios)
        assert any(s.reporter == "family_attendant" for s in scenarios)
        assert any(s.abandon_after is not None for s in scenarios)
        assert any("declined" in i for i in ids)

    def test_a_malformed_scenario_is_rejected(self) -> None:
        with pytest.raises(ScenarioError, match="requires 'id'"):
            Scenario.from_mapping({"patient_script": []})
        with pytest.raises(ScenarioError, match="requires 'ask'"):
            Scenario.from_mapping({"id": "x", "patient_script": [{"answer": "yes"}]})


class TestMetrics:
    def test_every_scenario_meets_its_clinical_expectations(
        self, scenarios: tuple[Scenario, ...], content: ClinicalContent
    ) -> None:
        _results, metrics = run_all(content, scenarios)
        assert metrics.failures == ()
        assert metrics.passed == metrics.scenarios

    def test_the_unsupported_assertion_rate_is_zero(
        self, scenarios: tuple[Scenario, ...], content: ClinicalContent
    ) -> None:
        """The one metric with a hard target. Not "low" — zero."""
        _results, metrics = run_all(content, scenarios)
        assert metrics.unsupported_assertion_rate == 0.0

    def test_required_field_recall_and_red_flag_recall_are_complete(
        self, scenarios: tuple[Scenario, ...], content: ClinicalContent
    ) -> None:
        _results, metrics = run_all(content, scenarios)
        assert metrics.required_field_recall == 1.0
        assert metrics.red_flag_recall == 1.0

    def test_no_false_positive_red_flag(
        self, scenarios: tuple[Scenario, ...], content: ClinicalContent
    ) -> None:
        _results, metrics = run_all(content, scenarios)
        assert metrics.red_flag_false_positive_rate == 0.0

    def test_the_machine_never_asks_another_complaint_s_questions(
        self, scenarios: tuple[Scenario, ...], content: ClinicalContent
    ) -> None:
        """The central claim: one pathway is activated and only its fields are
        asked, rather than every question the system knows."""
        results, metrics = run_all(content, scenarios)
        assert metrics.irrelevant_questions_per_session == 0.0
        for result in results:
            assert result.irrelevant_questions == (), result.scenario_id

    def test_the_run_is_reproducible(
        self, scenarios: tuple[Scenario, ...], content: ClinicalContent
    ) -> None:
        """Same scenarios in, same numbers out. Forever."""
        first = summarise(scenarios, tuple(run_scenario(s, content) for s in scenarios))
        second = summarise(scenarios, tuple(run_scenario(s, content) for s in scenarios))
        assert first == second

    def test_an_intake_completes_in_a_number_of_questions_a_patient_will_finish(
        self, scenarios: tuple[Scenario, ...], content: ClinicalContent
    ) -> None:
        """A history nobody finishes is not a history."""
        _results, metrics = run_all(content, scenarios)
        assert 0 < metrics.mean_questions_to_completion <= 90


class TestHarnessIsNotVacuous:
    """A green harness that cannot go red is worse than no harness."""

    def test_it_fails_when_an_expected_red_flag_does_not_fire(
        self, content: ClinicalContent
    ) -> None:
        scenario = Scenario.from_mapping(
            {
                "id": "sanity_missing_flag",
                "patient_script": [
                    {"ask": "preferred_language", "answer": "en"},
                    {"ask": "consent_given", "answer": "granted"},
                    {"ask": "chief_complaint", "answer": "fever"},
                ],
                "expect_red_flags": ["fever_with_meningism"],
                "abandon_after": 6,
                "expect_complete": False,
            }
        )
        result = run_scenario(scenario, content)
        assert not result.passed
        assert any("did not fire" in f for f in result.failures)

    def test_it_fails_when_a_forbidden_assertion_appears(
        self, content: ClinicalContent
    ) -> None:
        """The report legitimately contains the patient's own words; a scenario
        that forbids one of them must fail, proving the check reaches the text."""
        scenario = Scenario.from_mapping(
            {
                "id": "sanity_forbidden_phrase",
                "patient_script": [
                    {"ask": "preferred_language", "answer": "en"},
                    {"ask": "consent_given", "answer": "granted"},
                ],
                "forbid_assertions": ["DRAFT PRE-CONSULTATION INTAKE"],
                "abandon_after": 4,
                "expect_complete": False,
            }
        )
        result = run_scenario(scenario, content)
        assert not result.passed
        assert result.unsupported_assertions


class TestRunnerExitCodes:
    def test_a_clean_corpus_exits_zero(self) -> None:
        assert main(["--quiet"]) == 0

    def test_an_empty_scenario_directory_exits_non_zero(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        assert main(["--scenarios", str(tmp_path), "--quiet"]) == 2

    def test_json_output_is_machine_readable(self, capsys) -> None:  # type: ignore[no-untyped-def]
        import json

        assert main(["--json"]) == 0
        payload = json.loads(capsys.readouterr().out.split("\nOK:")[0])
        assert payload["metrics"]["scenarios"] >= MINIMUM_SCENARIOS
        assert payload["failures"] == []
