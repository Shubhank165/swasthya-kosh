"""The harness, tested by breaking it on purpose.

A harness that passes is worth nothing until it has been shown to fail. Every
test here takes a scenario that passes, breaks exactly one thing, and asserts
that the harness noticed — because a green evaluation run is only evidence if a
red one was reachable.

The scenario set itself is also run, so the shipped scenarios cannot rot.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.content import load_templates
from app.domain.record import FieldStatus
from app.domain.report.templates import TemplateRegistry
from evaluation.harness import run_scenario, summarise
from evaluation.run import SCENARIO_DIR
from evaluation.scenario import Scenario, ScenarioError, load_scenarios


@pytest.fixture(scope="module")
def templates() -> TemplateRegistry:
    settings = get_settings()
    return load_templates(
        settings.report_templates_dir,
        settings.report_languages,
        settings.default_report_language,
    )


@pytest.fixture(scope="module")
def scenarios() -> tuple[Scenario, ...]:
    return load_scenarios(SCENARIO_DIR)


def one(scenarios: tuple[Scenario, ...], scenario_id: str) -> Scenario:
    return next(s for s in scenarios if s.scenario_id == scenario_id)


class TestTheShippedScenarios:
    def test_they_all_pass(
        self, scenarios: tuple[Scenario, ...], templates: TemplateRegistry
    ) -> None:
        """The run that goes on a slide. If this breaks, either the pipeline
        regressed or a scenario stopped describing a real patient — and both
        are worth stopping for."""

        metrics = summarise(tuple(run_scenario(s, templates=templates) for s in scenarios))
        assert metrics.is_clean, metrics.failures

    def test_the_run_is_the_same_twice(
        self, scenarios: tuple[Scenario, ...], templates: TemplateRegistry
    ) -> None:
        """Two runs of the same scenarios must report identical numbers, or the
        harness cannot be used to compare two builds."""

        first = summarise(tuple(run_scenario(s, templates=templates) for s in scenarios))
        second = summarise(tuple(run_scenario(s, templates=templates) for s in scenarios))
        assert first == second

    def test_every_scenario_asserts_something(self, scenarios: tuple[Scenario, ...]) -> None:
        """A scenario with no expectations runs, passes, and proves nothing —
        which is worse than not having it, because it inflates the count."""

        for scenario in scenarios:
            assert (
                scenario.expect_fields
                or scenario.expect_red_flags
                or scenario.forbid_assertions
            ), f"{scenario.scenario_id} asserts nothing"


class TestItCanActuallyFail:
    def test_a_collapsed_status_is_caught(
        self, scenarios: tuple[Scenario, ...], templates: TemplateRegistry
    ) -> None:
        """The failure decision 1 exists for: a refusal read as a "no"."""

        scenario = one(scenarios, "five_statuses_01")
        broken = replace(
            scenario,
            expect_fields={**scenario.expect_fields, "tobacco": FieldStatus.ANSWERED},
        )
        result = run_scenario(broken, templates=templates)
        assert not result.passed
        assert any("tobacco" in failure for failure in result.failures)

    def test_a_missing_red_flag_is_caught(
        self, scenarios: tuple[Scenario, ...], templates: TemplateRegistry
    ) -> None:
        scenario = one(scenarios, "chest_pain_redflag_01")
        broken = replace(scenario, expect_red_flags=("RF_A_RULE_NOBODY_RAISED",))
        result = run_scenario(broken, templates=templates)
        assert not result.passed
        # Both directions: one expected and absent, one present and unexpected.
        assert result.flags_invented == 1
        assert any("was raised by the device and is not recorded" in f for f in result.failures)

    def test_a_lost_verbatim_phrase_is_caught(
        self, scenarios: tuple[Scenario, ...], templates: TemplateRegistry
    ) -> None:
        scenario = one(scenarios, "fever_hedged_duration_01")
        broken = replace(scenario, expect_verbatim=("something the patient never said",))
        result = run_scenario(broken, templates=templates)
        assert not result.passed
        assert result.verbatim_held == 0

    def test_a_forbidden_phrase_in_the_report_is_caught(
        self, scenarios: tuple[Scenario, ...], templates: TemplateRegistry
    ) -> None:
        """Proved with a phrase the report definitely contains, so the test is
        about the harness rather than about today's template wording."""

        scenario = one(scenarios, "fever_no_findings_01")
        result = run_scenario(scenario, templates=templates)
        present = result.answered  # sanity: the scenario produced a report at all
        assert present > 0

        broken = replace(scenario, forbid_assertions=("fever",))
        broken_result = run_scenario(broken, templates=templates)
        assert not broken_result.passed
        assert broken_result.forbidden_found == ("fever",)

    def test_a_field_that_is_not_there_at_all_is_caught(
        self, scenarios: tuple[Scenario, ...], templates: TemplateRegistry
    ) -> None:
        """Distinct from a wrong status, and the message says which. A field
        that never arrived and a field that arrived wrong are different bugs."""

        scenario = one(scenarios, "fever_no_findings_01")
        broken = replace(
            scenario,
            expect_fields={**scenario.expect_fields, "never_asked_about": FieldStatus.ANSWERED},
        )
        result = run_scenario(broken, templates=templates)
        assert any("is not in the record at all" in f for f in result.failures)


class TestSummarising:
    def test_a_rate_over_nothing_is_not_a_failure(self) -> None:
        """An empty denominator reports 1.0. Zero would say every assertion
        failed, when none was made."""

        metrics = summarise(())
        assert metrics.status_fidelity == 1.0
        assert metrics.red_flag_fidelity == 1.0
        assert metrics.is_clean

    def test_one_dirty_scenario_makes_the_whole_run_dirty(
        self, scenarios: tuple[Scenario, ...], templates: TemplateRegistry
    ) -> None:
        clean = [run_scenario(s, templates=templates) for s in scenarios]
        broken = run_scenario(
            replace(one(scenarios, "fever_no_findings_01"), forbid_assertions=("fever",)),
            templates=templates,
        )
        assert not summarise((*clean, broken)).is_clean


class TestLoading:
    def test_two_scenarios_cannot_share_an_id(self, tmp_path: Path) -> None:
        """One of them would be silently unreported, which is worse than either
        of them failing."""

        body = """
scenarios:
  - id: duplicate
    payload: {fields: {}}
  - id: duplicate
    payload: {fields: {}}
"""
        (tmp_path / "a.yaml").write_text(body, encoding="utf-8")
        with pytest.raises(ScenarioError, match="already"):
            load_scenarios(tmp_path)

    def test_an_unknown_status_is_refused_by_name(self, tmp_path: Path) -> None:
        """`present` was the old vocabulary. A scenario still using it must fail
        loudly rather than be mapped onto something in the new one."""

        body = """
scenarios:
  - id: old_vocabulary
    payload: {fields: {}}
    expect_fields: {chief_complaint: present}
"""
        (tmp_path / "a.yaml").write_text(body, encoding="utf-8")
        with pytest.raises(ScenarioError, match="unknown status"):
            load_scenarios(tmp_path)

    def test_an_empty_directory_is_an_error_not_an_empty_pass(self, tmp_path: Path) -> None:
        with pytest.raises(ScenarioError):
            load_scenarios(tmp_path)
