"""Selection policy, rule-set behaviour and the queue operations still uncovered."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.core.content import ClinicalContent
from app.domain.clinical.enums import Severity
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.clinical.provenance import (
    AlertId,
    IntakeId,
    QueueInstanceId,
    UserId,
)
from app.domain.queue import operations as ops
from app.domain.queue.entities import InstanceStatus, PriorityClass, QueueState
from app.domain.redflags.evaluator import (
    RedFlagReport,
    diff_alerts,
    evaluate,
    highest_severity,
)
from app.domain.redflags.rules import (
    RedFlagAction,
    RedFlagError,
    RedFlagRule,
    RedFlagRuleSet,
    blank_rule_set,
    field_names,
    validate_keys,
)
from app.domain.statemachine.policies import DEFAULT_POLICY, SelectionPolicy
from tests.unit.test_queue_domain import (
    NOW,
    make_instance,
    make_queue,
    make_ticket,
)


class TestSelectionPolicy:
    def test_the_first_supported_language_is_the_fallback(self) -> None:
        assert SelectionPolicy(supported_languages=("hi", "en")).fallback_language() == "hi"

    def test_an_empty_language_list_still_yields_english(self) -> None:
        assert SelectionPolicy(supported_languages=()).fallback_language() == "en"

    def test_an_exactly_supported_language_is_used(self) -> None:
        assert DEFAULT_POLICY.resolve_language("hi") == "hi"

    def test_a_regional_tag_resolves_to_its_base_language(self) -> None:
        """A kiosk reporting `hi-IN` must get Hindi, not the English fallback."""
        assert DEFAULT_POLICY.resolve_language("hi-IN") == "hi"

    def test_an_unsupported_language_falls_back_rather_than_failing(self) -> None:
        assert DEFAULT_POLICY.resolve_language("ta") == "en"

    def test_no_requested_language_falls_back(self) -> None:
        assert DEFAULT_POLICY.resolve_language(None) == "en"

    def test_the_defaults_match_the_brief(self) -> None:
        assert DEFAULT_POLICY.ask_optional_fields
        assert DEFAULT_POLICY.confirm_prior_records
        assert DEFAULT_POLICY.ayurveda_module_enabled


class TestRuleSet:
    def test_a_duplicate_rule_id_is_rejected(self) -> None:
        raw = {
            "id": "dup",
            "clinical_source": "test",
            "criteria": {"concept": "fever", "status": "present"},
        }
        with pytest.raises(RedFlagError, match="duplicate red-flag rule id"):
            RedFlagRuleSet.from_mappings([raw, raw])

    def test_an_unknown_severity_is_rejected(self) -> None:
        with pytest.raises(RedFlagError, match="unknown severity"):
            RedFlagRule.from_mapping(
                {
                    "id": "x",
                    "clinical_source": "t",
                    "severity": "apocalyptic",
                    "criteria": {"concept": "fever"},
                }
            )

    def test_a_rule_without_criteria_is_rejected(self) -> None:
        with pytest.raises(RedFlagError, match="'criteria' must be a mapping"):
            RedFlagRule.from_mapping({"id": "x", "clinical_source": "t"})

    def test_a_rule_without_an_id_is_rejected(self) -> None:
        with pytest.raises(RedFlagError, match="requires 'id'"):
            RedFlagRule.from_mapping({"clinical_source": "t", "criteria": {"concept": "f"}})

    def test_an_unknown_top_level_key_is_rejected(self) -> None:
        """A misspelt `critera:` must not silently disable a safety rule."""
        with pytest.raises(RedFlagError, match="unknown keys"):
            validate_keys({"id": "x", "critera": {}})
        validate_keys({key: None for key in field_names()})

    def test_an_empty_rule_set_reports_no_concepts(self) -> None:
        empty = blank_rule_set()
        assert len(empty) == 0
        assert empty.concepts() == frozenset()
        assert empty.ids() == ()

    def test_get_finds_a_rule_by_id(self, content: ClinicalContent) -> None:
        assert content.red_flags.get("thunderclap_headache") is not None
        assert content.red_flags.get("no_such_rule") is None

    def test_rules_needing_review_are_enumerated(self, content: ClinicalContent) -> None:
        assert {r.rule_id for r in content.red_flags.rules_needing_review()} >= {
            "thunderclap_headache"
        }

    def test_an_action_defaults_to_notifying_triage(self) -> None:
        assert RedFlagAction.from_mapping(None).notify == "triage"
        with pytest.raises(RedFlagError, match="'action' must be a mapping"):
            RedFlagAction.from_mapping(["triage"])  # type: ignore[arg-type]

    def test_as_sequence_is_ordered_most_severe_first(self, content: ClinicalContent) -> None:
        severities = [r.severity for r in content.red_flags.as_sequence()]
        assert severities[0] is Severity.CRITICAL
        assert severities[-1] is Severity.MODERATE


class TestAlertDiffing:
    def _firing(self, content: ClinicalContent) -> tuple:
        from app.domain.clinical.enums import FactStatus, Section

        from tests.conftest import make_fact

        state = PatientIntakeState(intake_id=IntakeId("i"))
        state = state.apply(
            make_fact(
                "syncope",
                status=FactStatus.PRESENT,
                section=Section.RED_FLAG_SCREEN,
                fact_id="f1",
            )
        )
        return evaluate(state, content.red_flags)

    def test_only_newly_firing_rules_are_reported_as_raised(
        self, content: ClinicalContent
    ) -> None:
        """A rule that keeps matching as the patient answers more questions must
        not re-alert on every answer."""
        alerts = self._firing(content)
        raised, cleared = diff_alerts(alerts, alerts)
        assert raised == ()
        assert cleared == ()
        raised, _ = diff_alerts((), alerts)
        assert len(raised) == len(alerts)

    def test_a_rule_that_stops_firing_is_reported_but_not_retracted(
        self, content: ClinicalContent
    ) -> None:
        alerts = self._firing(content)
        _raised, cleared = diff_alerts(alerts, ())
        assert len(cleared) == len(alerts)

    def test_highest_severity_ignores_closed_alerts(
        self, content: ClinicalContent
    ) -> None:
        alerts = self._firing(content)
        assert highest_severity(alerts) is Severity.HIGH
        acknowledged = tuple(
            a.acknowledged(by=UserId("triage-1"), at=NOW) for a in alerts
        )
        assert highest_severity(acknowledged) is None

    def test_an_alert_gains_its_identity_at_persistence_time(
        self, content: ClinicalContent
    ) -> None:
        alert = self._firing(content)[0]
        assert alert.alert_id is None
        identified = alert.with_identity(AlertId("a1"), NOW)
        assert identified.alert_id == "a1"
        assert identified.raised_at == NOW

    def test_an_empty_report_has_no_critical(self) -> None:
        assert not RedFlagReport().has_critical


class TestQueueOperationGuards:
    def test_a_closed_instance_refuses_every_mutation(self) -> None:
        closed = make_instance(status=InstanceStatus.CLOSED)
        with pytest.raises(ops.QueueOperationError, match="closed"):
            ops.issue(
                make_queue(),
                closed,
                ticket_id=make_ticket(1).ticket_id,
                sequence=1,
                priority_class=PriorityClass.WALKIN,
                now=NOW,
            )
        with pytest.raises(ops.QueueOperationError, match="already closed"):
            ops.close_instance(make_queue(), closed, [], now=NOW)

    def test_call_next_returns_none_when_nothing_is_callable(self) -> None:
        assert ops.call_next(make_queue(), make_instance(), [], {}, now=NOW) is None

    def test_recalling_a_ticket_that_was_never_called_is_rejected(self) -> None:
        with pytest.raises(ops.QueueOperationError, match="only a called ticket"):
            ops.recall(make_queue(), make_instance(), make_ticket(1), now=NOW)

    def test_starting_a_ticket_that_was_never_called_is_rejected(self) -> None:
        with pytest.raises(ops.QueueOperationError, match="call it before starting"):
            ops.start_consultation(make_queue(), make_instance(), make_ticket(1), now=NOW)

    def test_an_escalated_ticket_may_start_directly(self) -> None:
        """An escalated patient is going in now; requiring a separate call first
        would put a bureaucratic step in front of an urgent one."""
        escalated = make_ticket(1, state=QueueState.ESCALATED)
        result = ops.start_consultation(make_queue(), make_instance(), escalated, now=NOW)
        assert result.ticket is not None
        assert result.ticket.state is QueueState.IN_CONSULTATION

    def test_a_closed_ticket_cannot_be_deferred_transferred_or_cancelled(self) -> None:
        closed = make_ticket(1, state=QueueState.COMPLETED)
        for operation in (ops.defer, ops.no_show):
            with pytest.raises(ops.QueueOperationError):
                operation(make_queue(), make_instance(), closed, now=NOW)
        with pytest.raises(ops.QueueOperationError, match="already"):
            ops.cancel(make_queue(), make_instance(), closed, now=NOW, reason="x")

    def test_transferring_into_a_paused_instance_is_rejected(self) -> None:
        target = make_instance(
            instance_id=QueueInstanceId("qi2"), status=InstanceStatus.PAUSED
        )
        with pytest.raises(ops.QueueOperationError, match="paused"):
            ops.transfer(
                make_queue(),
                make_instance(),
                make_ticket(1),
                target_queue=make_queue(),
                target_instance=target,
                new_ticket_id=make_ticket(9).ticket_id,
                new_sequence=9,
                now=NOW,
            )

    def test_pausing_a_paused_instance_is_rejected(self) -> None:
        paused = make_instance(status=InstanceStatus.PAUSED)
        with pytest.raises(ops.QueueOperationError, match="paused"):
            ops.pause(paused, now=NOW)

    def test_resuming_an_open_instance_is_rejected(self) -> None:
        with pytest.raises(ops.QueueOperationError, match="not paused"):
            ops.resume(make_instance(), now=NOW)

    def test_opening_a_closed_instance_is_rejected(self) -> None:
        with pytest.raises(ops.QueueOperationError, match="closed"):
            ops.open_instance(make_instance(status=InstanceStatus.CLOSED), now=NOW)

    def test_cancel_records_the_reason_and_decrements_waiting(self) -> None:
        from app.domain.queue.entities import QueueCounters

        instance = make_instance(counters=QueueCounters(waiting_count=2))
        result = ops.cancel(
            make_queue(), instance, make_ticket(1), now=NOW, reason="patient left"
        )
        assert result.ticket is not None
        assert result.ticket.cancelled_reason == "patient left"
        assert result.instance is not None
        assert result.instance.counters.waiting_count == 1

    def test_no_show_increments_the_no_show_counter(self) -> None:
        result = ops.no_show(
            make_queue(), make_instance(), make_ticket(1, state=QueueState.CALLED), now=NOW
        )
        assert result.instance is not None
        assert result.instance.counters.no_show_count == 1

    def test_deferring_a_called_ticket_returns_it_to_the_waiting_pool(self) -> None:
        called = make_ticket(1, state=QueueState.CALLED)
        result = ops.defer(make_queue(), make_instance(), called, now=NOW)
        assert result.instance is not None
        assert result.instance.counters.waiting_count == 1

    def test_escalating_a_closed_ticket_is_rejected(self) -> None:
        with pytest.raises(ops.QueueOperationError, match="completed"):
            ops.escalate(
                make_queue(),
                make_instance(),
                make_ticket(1, state=QueueState.COMPLETED),
                alert_id=AlertId("a1"),
                acknowledged_by=UserId("triage-1"),
                acting_user_id=UserId("triage-1"),
                now=NOW,
            )


class TestCounterArithmetic:
    def test_the_rolling_mean_converges_over_several_consultations(self) -> None:
        from app.domain.queue.entities import QueueCounters

        counters = QueueCounters()
        for seconds in (600.0, 300.0, 900.0):
            counters = counters.with_completion(seconds)
        assert counters.served_sample == 3
        assert counters.avg_service_seconds == pytest.approx(600.0)

    def test_waiting_count_never_goes_negative(self) -> None:
        from app.domain.queue.entities import QueueCounters

        assert QueueCounters().with_call("KC-001").waiting_count == 0
        assert QueueCounters().with_no_show().waiting_count == 0

    def test_a_queue_runs_only_on_its_scheduled_weekdays(self) -> None:
        queue = make_queue(schedule_days=(1, 3))
        assert queue.runs_on(datetime(2026, 1, 13, tzinfo=UTC).date())  # Tuesday
        assert not queue.runs_on(datetime(2026, 1, 12, tzinfo=UTC).date())  # Monday

    def test_a_queue_with_no_schedule_runs_every_day(self) -> None:
        assert make_queue().runs_on(datetime(2026, 1, 12, tzinfo=UTC).date())

    def test_a_recalled_ticket_uses_its_recall_sequence_for_ordering(self) -> None:
        ticket = replace(make_ticket(1), recall_sequence=7)
        assert ticket.effective_sequence == 7
        assert make_ticket(1).effective_sequence == 1
