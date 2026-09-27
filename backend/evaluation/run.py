"""Evaluation entry point.

    python -m evaluation.run
    python -m evaluation.run --json

Prints the metrics table and exits non-zero on any failed scenario, any
unsupported assertion, any invented red flag, or any certainty this pipeline
raised on its own. Wired into `make`, so a regression in one of the promises
this codebase makes in writing fails the build exactly like a unit test.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.content import load_templates
from evaluation.harness import Metrics, ScenarioResult, run_scenario, summarise
from evaluation.scenario import Scenario, load_scenarios

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"


def run_all(scenarios: tuple[Scenario, ...]) -> tuple[tuple[ScenarioResult, ...], Metrics]:
    settings = get_settings()
    templates = load_templates(
        settings.report_templates_dir,
        settings.report_languages,
        settings.default_report_language,
    )
    results = tuple(run_scenario(s, templates=templates) for s in scenarios)
    return results, summarise(results)


def _table(metrics: Metrics) -> str:
    """The metrics table.

    Targets are printed beside the values, because a number without a target is
    a number nobody can act on — and the denominator is printed on the first
    row, because a rate over seven scenarios and a rate over seven hundred are
    not the same claim.
    """
    rows: list[tuple[str, str, str]] = [
        ("scenarios run", str(metrics.scenarios), ""),
        ("scenarios passed", f"{metrics.passed}/{metrics.scenarios}", "all"),
        ("status fidelity", f"{metrics.status_fidelity:.1%}", "100% (hard)"),
        ("certainty violations", str(metrics.certainty_violations), "0 (hard)"),
        ("verbatim retention", f"{metrics.verbatim_retention:.1%}", "100%"),
        ("red-flag fidelity", f"{metrics.red_flag_fidelity:.1%}", "100% (hard)"),
        ("invented red flags", str(metrics.invented_red_flags), "0 (hard)"),
        (
            "unsupported-assertion rate",
            f"{metrics.unsupported_assertion_rate:.2f}",
            "0.00 (hard)",
        ),
        ("forbidden phrases found", str(metrics.forbidden_phrase_hits), "0 (hard)"),
        ("mean coverage", f"{metrics.mean_coverage:.1%}", "context only"),
    ]
    width = max(len(label) for label, _, _ in rows)
    lines = [f"{label.ljust(width)}  {value:>10}  {target}" for label, value, target in rows]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the evaluation scenarios.")
    parser.add_argument(
        "--scenarios", type=Path, default=SCENARIO_DIR, help="scenario directory"
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    scenarios = load_scenarios(args.scenarios)
    results, metrics = run_all(scenarios)

    if args.json:
        print(
            json.dumps(
                {
                    "metrics": {
                        key: getattr(metrics, key)
                        for key in (
                            "scenarios",
                            "passed",
                            "status_fidelity",
                            "certainty_violations",
                            "verbatim_retention",
                            "red_flag_fidelity",
                            "invented_red_flags",
                            "unsupported_assertion_rate",
                            "forbidden_phrase_hits",
                            "mean_coverage",
                        )
                    },
                    "failures": list(metrics.failures),
                    "scenarios": [
                        {"id": r.scenario_id, "passed": r.passed, "failures": list(r.failures)}
                        for r in results
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(_table(metrics))
        if metrics.failures:
            # Every failure, not the first. A harness that stops at one turns a
            # single run into a queue of runs.
            print("\nfailures:")
            for failure in metrics.failures:
                print(f"  - {failure}")

    return 0 if metrics.is_clean else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
