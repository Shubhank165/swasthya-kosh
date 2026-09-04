"""Evaluation entry point.

    python -m evaluation.run

Prints the metrics table and exits non-zero on any unsupported assertion or any
failed scenario. Wired into CI, so a regression in clinical safety fails the
build exactly like a broken unit test.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.content import ClinicalContent, load_clinical_content
from evaluation.harness import Metrics, ScenarioResult, run_scenario, summarise
from evaluation.scenario import Scenario, load_scenarios

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"


def run_all(
    content: ClinicalContent, scenarios: tuple[Scenario, ...]
) -> tuple[tuple[ScenarioResult, ...], Metrics]:
    results = tuple(run_scenario(scenario, content) for scenario in scenarios)
    return results, summarise(scenarios, results)


def _table(metrics: Metrics) -> str:
    """The metrics table. Targets are printed beside the values, because a
    number without a target is a number nobody can act on."""
    rows: list[tuple[str, str, str]] = [
        ("scenarios run", str(metrics.scenarios), ""),
        ("scenarios passed", f"{metrics.passed}/{metrics.scenarios}", "all"),
        ("required-field recall", f"{metrics.required_field_recall:.1%}", "100%"),
        ("missing-field rate", f"{metrics.missing_field_rate:.1%}", "low"),
        (
            "irrelevant questions / session",
            f"{metrics.irrelevant_questions_per_session:.2f}",
            "0.00",
        ),
        (
            "unscripted questions / session",
            f"{metrics.unscripted_questions_per_session:.2f}",
            "script coverage",
        ),
        ("red-flag recall", f"{metrics.red_flag_recall:.1%}", "100%"),
        (
            "red-flag false-positive rate",
            f"{metrics.red_flag_false_positive_rate:.1%}",
            "0%",
        ),
        (
            "unsupported-assertion rate",
            f"{metrics.unsupported_assertion_rate:.2f}",
            "0.00 (hard)",
        ),
        ("questions to completion (mean)", f"{metrics.mean_questions_to_completion:.1f}", ""),
        ("completion rate", f"{metrics.completion_rate:.1%}", ""),
        ("mean coverage", f"{metrics.mean_coverage:.1f}%", ""),
    ]
    width = max(len(name) for name, _, _ in rows)
    lines = ["", "MediKiosk clinical evaluation", "=" * (width + 26)]
    lines.extend(f"{name:<{width}}  {value:>12}  {target}" for name, value, target in rows)
    lines.append("=" * (width + 26))
    return "\n".join(lines)


def _detail(results: tuple[ScenarioResult, ...]) -> str:
    lines = ["", "Per scenario", "-" * 78]
    for result in results:
        status = "pass" if result.passed else "FAIL"
        lines.append(
            f"[{status}] {result.scenario_id:<34} "
            f"{result.question_count:>3} asked  "
            f"coverage {result.coverage_percentage:>5.1f}%  "
            f"flags {len(result.fired_rules)}"
        )
        lines.extend(f"         - {failure}" for failure in result.failures)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MediKiosk clinical evaluation")
    parser.add_argument(
        "--scenarios", type=Path, default=SCENARIO_DIR, help="scenario directory"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument("--quiet", action="store_true", help="suppress per-scenario detail")
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="print the generated report for one scenario id and exit",
    )
    args = parser.parse_args(argv)

    settings: Settings = get_settings()
    content = load_clinical_content(settings)
    scenarios = load_scenarios(args.scenarios)
    if not scenarios:
        print(f"no scenarios found in {args.scenarios}", file=sys.stderr)
        return 2

    results, metrics = run_all(content, scenarios)

    if args.report:
        for result in results:
            if result.scenario_id == args.report:
                print(result.report_text)
                return 0
        print(f"unknown scenario '{args.report}'", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "metrics": {
                        "scenarios": metrics.scenarios,
                        "passed": metrics.passed,
                        "required_field_recall": metrics.required_field_recall,
                        "missing_field_rate": metrics.missing_field_rate,
                        "irrelevant_questions_per_session": (
                            metrics.irrelevant_questions_per_session
                        ),
                        "red_flag_recall": metrics.red_flag_recall,
                        "red_flag_false_positive_rate": metrics.red_flag_false_positive_rate,
                        "unsupported_assertion_rate": metrics.unsupported_assertion_rate,
                        "mean_questions_to_completion": metrics.mean_questions_to_completion,
                        "completion_rate": metrics.completion_rate,
                        "mean_coverage": metrics.mean_coverage,
                        "unscripted_questions_per_session": (
                            metrics.unscripted_questions_per_session
                        ),
                    },
                    "failures": list(metrics.failures),
                },
                indent=2,
            )
        )
    else:
        print(_table(metrics))
        if not args.quiet:
            print(_detail(results))
        if metrics.failures:
            print("\nFailures")
            print("-" * 78)
            for failure in metrics.failures:
                print(f"  {failure}")

    if metrics.unsupported_assertion_rate > 0.0:
        print(
            "\nFAIL: the report contained an unsupported assertion. "
            "The target for this metric is zero and it is not negotiable.",
            file=sys.stderr,
        )
        return 1
    if metrics.passed != metrics.scenarios:
        print(
            f"\nFAIL: {metrics.scenarios - metrics.passed} scenario(s) did not meet "
            "their clinical expectations.",
            file=sys.stderr,
        )
        return 1
    print("\nOK: every scenario met its clinical expectations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
