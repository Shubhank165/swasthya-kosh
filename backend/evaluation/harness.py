"""Replay harness: one scenario in, one measured result out.

Drives a synthetic kiosk payload through the real normaliser and the real report
builder, with no database and no providers, then measures what came out the far
end. Everything is in memory and deterministic, so a run takes milliseconds and
can sit in CI beside the unit tests.

**What this measures, and why the list is shorter than it used to be.** The
harness this replaces drove a state machine that chose the next question, and
reported question-selection numbers — irrelevant questions per session, turns to
completion, red-flag recall. That machine runs on the Jetson now. Reporting
those numbers from this backend would be reporting numbers about code that is
not here, which is worse than reporting none. So what is measured is what this
backend is actually answerable for:

- **Status fidelity.** All five statuses survive normalisation. Decision 1 says
  `unresolved`, `not_asked`, `not_applicable` and `refused` may never collapse
  into each other or into a "no", and this is the number that says they did not.
- **Certainty.** Nothing arrives more certain than it was sent. Decision 2 lets
  only a named human raise it.
- **Verbatim retention.** The patient's own words are still in the record. A
  pipeline that keeps the coded value and loses the phrase has lost the only
  thing a physician can check the coding against.
- **Red-flag fidelity.** Every criterion the device raised is recorded, and none
  that it did not. The backend evaluates no rules; this is the number that says
  it still does not.
- **Unsupported assertions.** Every forbidden phrase found in the rendered
  report. The target is zero and there is no other acceptable value.

Nothing here is a quality score for the clinical content. It is a regression
guard on the promises this codebase makes in writing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.domain.clinical.enums import Certainty, certainty_rank
from app.domain.record import CanonicalRecord, FieldStatus
from app.domain.report import builder
from app.domain.report.safety import find_unsupported_assertions
from app.domain.report.templates import TemplateRegistry
from app.normalize.registry import normalize
from evaluation.scenario import Scenario

#: Fixed, so two runs on two machines produce identical reports to diff.
CLOCK = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)

HOSPITAL_ID = "eval-hospital"


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """What happened to one scenario, and everything that was wrong with it."""

    scenario_id: str
    #: Expected statuses that survived, over expected statuses asserted.
    statuses_held: int = 0
    statuses_expected: int = 0
    #: Verbatim phrases still present, over phrases asserted.
    verbatim_held: int = 0
    verbatim_expected: int = 0
    #: Red flags recorded as sent.
    flags_held: int = 0
    flags_expected: int = 0
    #: Criteria in the record that the scenario never raised. Should be zero
    #: always: the backend runs no rules and may not invent one.
    flags_invented: int = 0
    #: Facts whose certainty is higher than the payload claimed.
    certainty_raised: int = 0
    answered: int = 0
    fields_total: int = 0
    unsupported: tuple[str, ...] = ()
    forbidden_found: tuple[str, ...] = ()
    failures: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return not self.failures


def _payload_for(scenario: Scenario) -> dict[str, Any]:
    """The scenario's payload with the identifiers a kiosk would have set.

    Derived from the scenario id by digest rather than by `hash()`, which is
    salted per process: the same scenario has to produce the same intake id on
    every machine and in every run, or two reports of the same patient are not
    comparable and the determinism this harness claims is not real.
    """
    stem = hashlib.sha256(scenario.scenario_id.encode("utf-8")).hexdigest()[:32]
    intake_id = f"{stem[:8]}-{stem[8:12]}-4{stem[13:16]}-8{stem[17:20]}-{stem[20:32]}"
    return {
        "schema_version": "0.1",
        "intake_id": intake_id,
        "kiosk_id": "eval-kiosk",
        "hospital_id": HOSPITAL_ID,
        "started_at": CLOCK.isoformat(),
        "completed_at": CLOCK.isoformat(),
        "status": "complete",
        "language": scenario.language,
        **dict(scenario.payload),
    }


def _declared_certainty(payload: dict[str, Any], field_id: str) -> Certainty:
    """The strongest certainty the payload licenses for one field.

    A kiosk field carries no certainty of its own; the normaliser derives one.
    `REPORTED` is the ceiling for anything a patient said about themselves, and
    a hedged answer must come out at or below it — never above.
    """
    fields = payload.get("fields") or {}
    entry = fields.get(field_id) if isinstance(fields, dict) else None
    if isinstance(entry, dict) and entry.get("certainty"):
        return Certainty(str(entry["certainty"]))
    return Certainty.REPORTED


def run_scenario(scenario: Scenario, *, templates: TemplateRegistry) -> ScenarioResult:
    """Normalise, build, render, measure."""
    payload = _payload_for(scenario)
    failures: list[str] = []

    record: CanonicalRecord = normalize(payload, now=CLOCK)

    # --- statuses -----------------------------------------------------------
    by_field = {fact.field_id: fact for fact in record.live_facts()}
    statuses_held = 0
    for field_id, expected in scenario.expect_fields.items():
        fact = by_field.get(field_id)
        if fact is None:
            failures.append(f"field {field_id!r} is not in the record at all")
            continue
        if fact.status is expected:
            statuses_held += 1
        else:
            # Named both ways round: "arrived as X, should be Y" is the sentence
            # somebody debugging a collapsed status needs.
            failures.append(
                f"field {field_id!r} arrived as {fact.status.value!r}, "
                f"scenario expects {expected.value!r}"
            )

    # --- certainty ----------------------------------------------------------
    certainty_raised = 0
    for fact in record.live_facts():
        ceiling = _declared_certainty(payload, fact.field_id)
        if certainty_rank(fact.certainty) > certainty_rank(ceiling):
            certainty_raised += 1
            failures.append(
                f"field {fact.field_id!r} came out {fact.certainty.value!r} "
                f"from a payload that licenses at most {ceiling.value!r}"
            )

    # --- verbatim -----------------------------------------------------------
    spoken = " ".join(
        fact.original_text for fact in record.live_facts() if fact.original_text
    )
    verbatim_held = 0
    for phrase in scenario.expect_verbatim:
        if phrase in spoken:
            verbatim_held += 1
        else:
            failures.append(f"the patient's words {phrase!r} are not in the record")

    # --- red flags ----------------------------------------------------------
    recorded = {event.rule_id for event in record.red_flags}
    expected_flags = set(scenario.expect_red_flags)
    flags_held = len(expected_flags & recorded)
    for missing in sorted(expected_flags - recorded):
        failures.append(f"red flag {missing!r} was raised by the device and is not recorded")
    invented = sorted(recorded - expected_flags)
    for extra in invented:
        # The backend evaluates no rules. A criterion here that the scenario did
        # not send is this system having decided something, which is the one
        # thing it is not allowed to do.
        failures.append(f"red flag {extra!r} is in the record and was never raised")

    # --- the rendered report ------------------------------------------------
    language = templates.resolve(record.language)
    report = builder.build(record, templates=language)
    text = builder.render_text(report, language)

    unsupported = find_unsupported_assertions(text)
    for phrase in unsupported:
        failures.append(f"the report asserts {phrase!r}")

    lowered = text.lower()
    forbidden = tuple(p for p in scenario.forbid_assertions if p.lower() in lowered)
    for phrase in forbidden:
        failures.append(f"the report contains the forbidden phrase {phrase!r}")

    live = record.live_facts()
    return ScenarioResult(
        scenario_id=scenario.scenario_id,
        statuses_held=statuses_held,
        statuses_expected=len(scenario.expect_fields),
        verbatim_held=verbatim_held,
        verbatim_expected=len(scenario.expect_verbatim),
        flags_held=flags_held,
        flags_expected=len(expected_flags),
        flags_invented=len(invented),
        certainty_raised=certainty_raised,
        answered=sum(1 for f in live if f.status is FieldStatus.ANSWERED),
        fields_total=len(live),
        unsupported=unsupported,
        forbidden_found=forbidden,
        failures=tuple(failures),
    )


@dataclass(frozen=True, slots=True)
class Metrics:
    """The reported table.

    `unsupported_assertion_rate` and `invented_red_flags` have a target of zero
    and no other acceptable value. The rest are rates over what the scenarios
    asserted, and a rate over nothing is reported as 1.0 rather than 0.0 — an
    empty scenario set must not read as a total failure, and `scenarios` is on
    the table so nobody quotes a rate without its denominator.
    """

    scenarios: int
    passed: int
    status_fidelity: float
    certainty_violations: int
    verbatim_retention: float
    red_flag_fidelity: float
    invented_red_flags: int
    unsupported_assertion_rate: float
    forbidden_phrase_hits: int
    mean_coverage: float
    failures: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_clean(self) -> bool:
        """Every scenario passed and nothing was asserted, invented or raised."""
        return (
            self.passed == self.scenarios
            and self.unsupported_assertion_rate == 0.0
            and self.invented_red_flags == 0
            and self.certainty_violations == 0
            and self.forbidden_phrase_hits == 0
        )


def _rate(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else round(numerator / denominator, 4)


def summarise(results: tuple[ScenarioResult, ...]) -> Metrics:
    """Aggregate scenario results into the reported metrics."""
    coverage = [
        result.answered / result.fields_total
        for result in results
        if result.fields_total
    ]
    return Metrics(
        scenarios=len(results),
        passed=sum(1 for r in results if r.passed),
        status_fidelity=_rate(
            sum(r.statuses_held for r in results),
            sum(r.statuses_expected for r in results),
        ),
        certainty_violations=sum(r.certainty_raised for r in results),
        verbatim_retention=_rate(
            sum(r.verbatim_held for r in results),
            sum(r.verbatim_expected for r in results),
        ),
        red_flag_fidelity=_rate(
            sum(r.flags_held for r in results),
            sum(r.flags_expected for r in results),
        ),
        invented_red_flags=sum(r.flags_invented for r in results),
        unsupported_assertion_rate=round(
            0.0 if not results else sum(1 for r in results if r.unsupported) / len(results),
            4,
        ),
        forbidden_phrase_hits=sum(len(r.forbidden_found) for r in results),
        mean_coverage=round(sum(coverage) / len(coverage), 4) if coverage else 0.0,
        failures=tuple(
            f"{r.scenario_id}: {failure}" for r in results for failure in r.failures
        ),
    )
