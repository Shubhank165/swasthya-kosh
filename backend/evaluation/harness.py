"""Replay harness.

Drives a scripted patient through the real state machine with mock providers and
no database, then measures what happened. This is a deliverable, not a test
utility: it is what turns "the system asks the right questions" into a number
anyone can reproduce.

Everything is in memory and deterministic. A run takes milliseconds, so it can
sit in CI beside the unit tests and fail the build on a clinical-safety
regression exactly like any other test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.content import ClinicalContent
from app.core.ids import SequentialIdFactory
from app.domain.clinical.enums import (
    AnswerShape,
    Certainty,
    FactStatus,
    ReporterRole,
    Section,
    SourceType,
    Temporality,
)
from app.domain.clinical.fact import ClinicalFact
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.clinical.provenance import (
    CodedValue,
    ConceptRef,
    DocumentId,
    Duration,
    FactId,
    IntakeId,
    Quantity,
    ScaleValue,
    SegmentId,
    SourceRef,
    TextValue,
)
from app.domain.contradictions.detector import detect
from app.domain.coverage.coverage import compute
from app.domain.redflags.evaluator import evaluate
from app.domain.statemachine.engine import ClinicalStateMachine, Complete, Step
from app.domain.summary.builder import build
from app.domain.summary.templates import find_unsupported_assertions
from evaluation.scenario import Scenario, ScriptedTurn

#: Hard stop, so a content bug that loops cannot hang CI.
MAX_TURNS = 200


@dataclass(frozen=True, slots=True)
class AskedQuestion:
    """One question the machine put, and where it came from."""

    concept: str
    section: Section
    origin: str
    source_pathway: str
    answered: bool
    selection_reason: str


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Everything measured for one scenario."""

    scenario_id: str
    asked: tuple[AskedQuestion, ...]
    completed: bool
    coverage_percentage: float
    missing_required: tuple[str, ...]
    fired_rules: tuple[str, ...]
    contradictions: tuple[str, ...]
    unsupported_assertions: tuple[str, ...]
    failures: tuple[str, ...]
    report_text: str
    #: Complaint pathway in force at the end of the run.
    active_pathway: str | None = None
    #: Review-of-systems groups the active pathway declared.
    active_ros_groups: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.failures

    @property
    def question_count(self) -> int:
        return len(self.asked)

    @property
    def irrelevant_questions(self) -> tuple[str, ...]:
        """Questions belonging to a complaint the patient does not have.

        This is the claim being measured: the machine activates one pathway and
        asks only that pathway's fields, rather than every question it knows.
        A patient with chest pain must never be asked about morning joint
        stiffness, and this counts the times that happened.

        Deliberately *not* "questions the script had no answer for" — that
        measures how complete the test script is, not how relevant the machine
        is, and it would fall as the scripts grew rather than as the system
        improved.
        """
        return tuple(
            q.concept
            for q in self.asked
            if q.origin == "pathway"
            and self.active_pathway is not None
            and q.source_pathway != self.active_pathway
        )

    @property
    def unscripted_questions(self) -> tuple[str, ...]:
        """Questions the script had no answer for. Script coverage, reported for
        context so a low number is not mistaken for a relevance result."""
        return tuple(q.concept for q in self.asked if not q.answered)


def _language_of(scenario: Scenario, turn: ScriptedTurn) -> str:
    return turn.lang or scenario.language


def _coerce(step: Step, raw: Any) -> tuple[FactStatus, Any]:
    """Turn a scripted answer into a (status, value) pair for the step's shape.

    Mirrors `app.services.answers`, deliberately: the harness must exercise the
    same semantics the API does, or its numbers describe a system nobody runs.
    """
    if raw is None:
        return FactStatus.UNKNOWN, None
    text = str(raw).strip().lower()
    if step.answer.shape in {AnswerShape.YES_NO_UNKNOWN, AnswerShape.CONFIRMATION}:
        if text in {"yes", "true", "present", "correct"}:
            return FactStatus.PRESENT, None
        if text in {"no", "false", "absent"}:
            return FactStatus.ABSENT, None
        return FactStatus.UNKNOWN, None
    if text in {"unknown", "not_sure", "dont_know"}:
        return FactStatus.UNKNOWN, None

    shape = step.answer.shape
    if shape is AnswerShape.SCALE:
        return FactStatus.PRESENT, ScaleValue(
            float(raw), step.answer.minimum or 0.0, step.answer.maximum or 10.0
        )
    if shape is AnswerShape.DURATION:
        if isinstance(raw, dict):
            return FactStatus.PRESENT, Duration(float(raw["magnitude"]), str(raw["unit"]))
        magnitude, unit = str(raw).split()
        return FactStatus.PRESENT, Duration(float(magnitude), unit)
    if shape is AnswerShape.QUANTITY:
        if isinstance(raw, dict):
            return FactStatus.PRESENT, Quantity(
                float(raw["magnitude"]), str(raw.get("unit", step.answer.unit or "unit"))
            )
        return FactStatus.PRESENT, Quantity(float(raw), step.answer.unit or "unit")
    if shape in {AnswerShape.SINGLE_CHOICE, AnswerShape.MULTI_CHOICE}:
        if isinstance(raw, list):
            return FactStatus.PRESENT, CodedValue(code=",".join(str(v) for v in raw))
        return FactStatus.PRESENT, CodedValue(code=str(raw))
    return FactStatus.PRESENT, TextValue(str(raw))


def _prior_fact(
    entry: dict[str, Any], content: ClinicalContent, *, fact_id: str, now: datetime
) -> ClinicalFact:
    """Build an injected prior-record or document fact."""
    concept_id = str(entry["concept"])
    concept = content.concepts.get(concept_id)
    source = SourceType(str(entry.get("source", "prior_record")))
    if source is SourceType.DOCUMENT:
        ref = SourceRef.from_document(
            DocumentId(str(entry.get("document_id", "Discharge_summary_1.jpg"))), page=1
        )
    else:
        ref = SourceRef.from_actor("prior_record")
    value_text = entry.get("value")
    return ClinicalFact(
        fact_id=FactId(fact_id),
        concept=concept.ref() if concept else ConceptRef(concept_id),
        status=FactStatus(str(entry.get("status", "present"))),
        certainty=Certainty(str(entry.get("certainty", "reported"))),
        temporality=Temporality.HISTORICAL,
        source_type=source,
        source_ref=ref,
        confidence=float(entry.get("confidence", 0.9)),
        reported_by=ReporterRole.STAFF,
        recorded_at=now,
        section=concept.section if concept else Section.PAST_MEDICAL,
        value=TextValue(str(value_text)) if value_text is not None else None,
    )


def run_scenario(scenario: Scenario, content: ClinicalContent) -> ScenarioResult:
    """Drive one scenario and measure the outcome."""
    machine = ClinicalStateMachine(content.content_set)
    ids = SequentialIdFactory()
    now = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)

    state = PatientIntakeState(intake_id=IntakeId(scenario.scenario_id))
    state = state.with_language(scenario.language).with_reporter(
        ReporterRole(scenario.reporter)
    )
    for entry in scenario.prior_facts:
        now += timedelta(seconds=1)
        state = state.apply_record(
            _prior_fact(dict(entry), content, fact_id=ids.new_id("prior"), now=now)
        )

    script = {turn.ask: turn for turn in scenario.patient_script}
    asked: list[AskedQuestion] = []

    for _ in range(MAX_TURNS):
        if scenario.abandon_after is not None and len(asked) >= scenario.abandon_after:
            break

        # Settle gated fields exactly as the service does, so coverage has a
        # real denominator rather than a hole.
        for planned, reason in machine.pending_not_applicable(state):
            now += timedelta(seconds=1)
            state = state.apply(
                ClinicalFact(
                    fact_id=FactId(ids.new_id("na")),
                    concept=content.concepts.ref(planned.concept),
                    status=FactStatus.NOT_APPLICABLE,
                    certainty=Certainty.CONFIRMED,
                    temporality=Temporality.CURRENT,
                    source_type=SourceType.DERIVED,
                    source_ref=SourceRef.from_actor("state_machine"),
                    confidence=1.0,
                    reported_by=ReporterRole.STAFF,
                    recorded_at=now,
                    section=planned.section,
                    note=f"precondition not satisfied: {reason}",
                )
            )

        step = machine.next_step(state)
        if isinstance(step, Complete):
            break

        turn = script.get(step.concept)
        asked.append(
            AskedQuestion(
                concept=step.concept,
                section=step.section,
                origin=step.origin.value,
                source_pathway=step.source_pathway,
                answered=turn is not None,
                selection_reason=step.selection_reason,
            )
        )
        now += timedelta(seconds=1)

        if turn is not None and turn.declined:
            state = state.with_declined(step.concept)
            continue

        raw = turn.answer if turn is not None else None
        status, value = _coerce(step, raw)
        language = _language_of(scenario, turn) if turn else scenario.language
        source = SourceType(turn.source) if turn else SourceType.TOUCH
        live = state.fact_for(step.concept)

        fact = ClinicalFact(
            fact_id=FactId(ids.new_id("fact")),
            concept=content.concepts.ref(step.concept),
            status=status,
            # Nothing the harness produces is CONFIRMED: no human confirmed it.
            certainty=Certainty.REPORTED,
            temporality=Temporality.CURRENT,
            source_type=source,
            source_ref=(
                SourceRef.from_transcript(SegmentId(f"seg-{len(asked)}"), 0, 1200)
                if source is SourceType.VOICE
                else SourceRef.from_actor(source.value)
            ),
            confidence=turn.confidence if turn else 1.0,
            reported_by=state.reporter,
            recorded_at=now,
            section=step.section,
            value=value,
            # Only a scripted utterance becomes the verbatim expression. A coded
            # option is the system's token, not the patient's words.
            original_expression=turn.said if turn is not None else None,
            original_language=language,
            supersedes=live.fact_id if live is not None else None,
        )
        state = state.apply(fact)

        # The chief-complaint answer pins the pathway and restates itself as a
        # fact about the complaint, exactly as the service does.
        if step.concept == content.content_set.chief_complaint_concept and isinstance(
            value, CodedValue
        ):
            pathway = content.pathways.match_or_fallback(value.code)
            state = state.with_pathway(pathway.pathway_id, pathway.review_of_systems)
            if value.code in content.concepts:
                now += timedelta(seconds=1)
                complaint = content.concepts.require(value.code)
                existing = state.fact_for(value.code)
                state = state.apply(
                    ClinicalFact(
                        fact_id=FactId(ids.new_id("fact")),
                        concept=complaint.ref(),
                        status=FactStatus.PRESENT,
                        certainty=Certainty.REPORTED,
                        temporality=Temporality.CURRENT,
                        source_type=source,
                        source_ref=fact.source_ref,
                        confidence=fact.confidence,
                        reported_by=state.reporter,
                        recorded_at=now,
                        section=Section.CHIEF_COMPLAINT,
                        original_expression=fact.original_expression,
                        original_language=fact.original_language,
                        supersedes=existing.fact_id if existing else None,
                        note=f"derived from chief_complaint={value.code}",
                    )
                )

    # --- measure ------------------------------------------------------------

    coverage = compute(state, machine.plan(state))
    alerts = evaluate(state, content.red_flags)
    conflicts = detect(state)
    summary = build(state, coverage=coverage, conflicts=conflicts, alerts=alerts)
    report_text = summary.render_text()

    fired = tuple(a.rule_id for a in alerts)
    asked_concepts = {q.concept for q in asked}
    completed = isinstance(machine.next_step(state), Complete)

    failures: list[str] = []

    for expected in scenario.expect_facts:
        actual = state.status_of(expected.concept)
        if actual is not expected.status:
            failures.append(
                f"fact {expected.concept}: expected {expected.status}, got {actual}"
            )
        elif expected.value is not None and state.value_of(expected.concept) != expected.value:
            failures.append(
                f"fact {expected.concept}: expected value {expected.value!r}, "
                f"got {state.value_of(expected.concept)!r}"
            )

    for concept in scenario.expect_required_questions:
        if concept not in asked_concepts:
            failures.append(f"required question never asked: {concept}")

    for rule_id in scenario.expect_red_flags:
        if rule_id not in fired:
            failures.append(f"red flag did not fire: {rule_id}")

    for rule_id in scenario.forbid_red_flags:
        if rule_id in fired:
            failures.append(f"red flag fired when it should not have: {rule_id}")

    for concept in scenario.expect_contradictions:
        if concept not in {c.concept for c in conflicts}:
            failures.append(f"contradiction not surfaced: {concept}")

    lowered = report_text.lower()
    scripted_hits = tuple(p for p in scenario.forbid_assertions if p.lower() in lowered)
    global_hits = find_unsupported_assertions(report_text)
    unsupported = tuple(dict.fromkeys((*scripted_hits, *global_hits)))
    failures.extend(f"unsupported assertion in report: {phrase!r}" for phrase in unsupported)

    if scenario.expect_complete and not completed:
        failures.append(
            "intake did not complete; missing "
            f"{[m.concept for m in coverage.missing_required()]}"
        )
    if not scenario.expect_complete and completed:
        failures.append("intake completed but the scenario expected it to remain open")

    return ScenarioResult(
        scenario_id=scenario.scenario_id,
        asked=tuple(asked),
        completed=completed,
        coverage_percentage=coverage.percentage,
        missing_required=tuple(m.concept for m in coverage.missing_required()),
        fired_rules=fired,
        contradictions=tuple(c.concept for c in conflicts),
        unsupported_assertions=unsupported,
        failures=tuple(failures),
        report_text=report_text,
        active_pathway=state.active_pathway,
        active_ros_groups=state.active_ros_groups,
    )


@dataclass(frozen=True, slots=True)
class Metrics:
    """The reported table.

    These are the numbers that convert a pitch claim into something checkable.
    `unsupported_assertion_rate` has a target of zero and nothing else; a
    non-zero value fails the build.
    """

    scenarios: int
    passed: int
    required_field_recall: float
    missing_field_rate: float
    irrelevant_questions_per_session: float
    red_flag_recall: float
    red_flag_false_positive_rate: float
    unsupported_assertion_rate: float
    mean_questions_to_completion: float
    completion_rate: float
    mean_coverage: float
    #: Script coverage, reported for context rather than as a quality signal.
    unscripted_questions_per_session: float = 0.0
    failures: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_clean(self) -> bool:
        """No unsupported assertion anywhere, and every scenario passed."""
        return self.unsupported_assertion_rate == 0.0 and self.passed == self.scenarios


def _rate(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else round(numerator / denominator, 4)


def summarise(
    scenarios: tuple[Scenario, ...], results: tuple[ScenarioResult, ...]
) -> Metrics:
    """Aggregate scenario results into the reported metrics."""
    required_expected = required_asked = 0
    flags_expected = flags_fired = 0
    forbidden_flags = forbidden_fired = 0
    irrelevant = 0
    unscripted = 0
    completed_counts: list[int] = []
    unsupported = 0

    for scenario, result in zip(scenarios, results, strict=True):
        asked_concepts = {q.concept for q in result.asked}
        required_expected += len(scenario.expect_required_questions)
        required_asked += sum(
            1 for concept in scenario.expect_required_questions if concept in asked_concepts
        )
        flags_expected += len(scenario.expect_red_flags)
        flags_fired += sum(1 for r in scenario.expect_red_flags if r in result.fired_rules)
        forbidden_flags += len(scenario.forbid_red_flags)
        forbidden_fired += sum(1 for r in scenario.forbid_red_flags if r in result.fired_rules)
        irrelevant += len(result.irrelevant_questions)
        unscripted += len(result.unscripted_questions)
        unsupported += len(result.unsupported_assertions)
        if result.completed:
            completed_counts.append(result.question_count)

    total = len(results)
    return Metrics(
        scenarios=total,
        passed=sum(1 for r in results if r.passed),
        required_field_recall=_rate(required_asked, required_expected),
        missing_field_rate=_rate(
            sum(len(r.missing_required) for r in results),
            sum(len(r.asked) + len(r.missing_required) for r in results),
        ),
        irrelevant_questions_per_session=round(irrelevant / total, 2) if total else 0.0,
        red_flag_recall=_rate(flags_fired, flags_expected),
        red_flag_false_positive_rate=_rate(forbidden_fired, forbidden_flags),
        unsupported_assertion_rate=_rate(unsupported, total),
        mean_questions_to_completion=(
            round(sum(completed_counts) / len(completed_counts), 1) if completed_counts else 0.0
        ),
        completion_rate=_rate(len(completed_counts), total),
        mean_coverage=round(sum(r.coverage_percentage for r in results) / total, 1)
        if total
        else 0.0,
        unscripted_questions_per_session=round(unscripted / total, 2) if total else 0.0,
        failures=tuple(
            f"{r.scenario_id}: {failure}" for r in results for failure in r.failures
        ),
    )
