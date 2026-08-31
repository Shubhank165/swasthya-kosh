"""Queue ordering, policies and operations — all pure, all in memory."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.clinical.enums import IntakeState
from app.domain.clinical.provenance import (
    IntakeId,
    QueueId,
    QueueInstanceId,
    TicketId,
    UserId,
)
from app.domain.queue import operations as ops
from app.domain.queue.entities import (
    AssignmentPolicy,
    InstanceStatus,
    PriorityClass,
    Queue,
    QueueCounters,
    QueueInstance,
    QueueState,
    SessionName,
    Ticket,
    UnservedPolicy,
)
from app.domain.queue.ordering import (
    estimated_wait_minutes,
    order,
    position_of,
    select_next,
)
from app.domain.queue.policies import (
    ClosurePolicy,
    PatientAttributes,
    PriorityPolicy,
    QueuePolicySet,
    RecallPolicy,
    honoured_classes,
)

NOW = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


def make_queue(**overrides: object) -> Queue:
    defaults: dict[str, object] = {
        "queue_id": QueueId("q1"),
        "name": "Kayachikitsa General OPD",
        "department_code": "KC",
        "service_point": "OPD-1",
        "assignment_policy": AssignmentPolicy.POOLED_BY_DEPARTMENT,
        "token_prefix": "KC",
    }
    defaults.update(overrides)
    return Queue(**defaults)  # type: ignore[arg-type]


def make_instance(**overrides: object) -> QueueInstance:
    defaults: dict[str, object] = {
        "instance_id": QueueInstanceId("qi1"),
        "queue_id": QueueId("q1"),
        "service_date": date(2026, 1, 15),
        "session": SessionName.MORNING,
        "status": InstanceStatus.OPEN,
    }
    defaults.update(overrides)
    return QueueInstance(**defaults)  # type: ignore[arg-type]


def make_ticket(
    sequence: int,
    *,
    priority: PriorityClass = PriorityClass.WALKIN,
    state: QueueState = QueueState.WAITING,
    intake_id: str | None = None,
    appointment: datetime | None = None,
    issued_at: datetime | None = None,
    overtaken: int = 0,
    recall_sequence: int | None = None,
) -> Ticket:
    return Ticket(
        ticket_id=TicketId(f"t{sequence}"),
        queue_id=QueueId("q1"),
        instance_id=QueueInstanceId("qi1"),
        token_number=f"KC-{sequence:03d}",
        token_sequence=sequence,
        priority_class=priority,
        state=state,
        issued_at=issued_at or NOW,
        intake_id=IntakeId(intake_id) if intake_id else None,
        appointment_slot_time=appointment,
        overtaken_count=overtaken,
        recall_sequence=recall_sequence,
    )


class TestOrdering:
    def test_priority_class_beats_token_sequence(self) -> None:
        tickets = [make_ticket(1), make_ticket(2, priority=PriorityClass.EMERGENCY)]
        assert [t.token_sequence for t in order(tickets)] == [2, 1]

    def test_appointment_time_breaks_ties_within_a_class(self) -> None:
        later = make_ticket(
            1, priority=PriorityClass.APPOINTMENT, appointment=NOW + timedelta(hours=2)
        )
        earlier = make_ticket(2, priority=PriorityClass.APPOINTMENT, appointment=NOW)
        assert [t.token_sequence for t in order([later, earlier])] == [2, 1]

    def test_a_walk_in_never_displaces_a_booked_slot(self) -> None:
        """A walk-in has no appointment time; it must sort after every real one
        rather than before them."""
        walkin = make_ticket(1, priority=PriorityClass.APPOINTMENT)
        booked = make_ticket(5, priority=PriorityClass.APPOINTMENT, appointment=NOW)
        assert order([walkin, booked])[0].token_sequence == 5

    def test_token_sequence_breaks_the_final_tie(self) -> None:
        assert [t.token_sequence for t in order([make_ticket(3), make_ticket(1)])] == [1, 3]

    def test_closed_tickets_are_not_orderable(self) -> None:
        assert order([make_ticket(1, state=QueueState.COMPLETED)]) == ()

    def test_full_precedence_order(self) -> None:
        tickets = [
            make_ticket(1),
            make_ticket(2, priority=PriorityClass.APPOINTMENT, appointment=NOW),
            make_ticket(3, priority=PriorityClass.PRIORITY),
            make_ticket(4, priority=PriorityClass.EMERGENCY),
        ]
        assert [t.priority_class for t in order(tickets)] == [
            PriorityClass.EMERGENCY,
            PriorityClass.PRIORITY,
            PriorityClass.APPOINTMENT,
            PriorityClass.WALKIN,
        ]


class TestPreferIntakeReady:
    def test_it_is_off_by_default(self) -> None:
        queue = make_queue()
        assert not queue.prefer_intake_ready
        selection = select_next(
            [make_ticket(1), make_ticket(2, intake_id="i2")],
            queue,
            make_instance(),
            {IntakeId("i2"): IntakeState.READY},
        )
        assert selection is not None
        assert selection.ticket.token_sequence == 1
        assert selection.passed_over == ()

    def test_a_ready_intake_is_taken_ahead_within_the_window(self) -> None:
        """Keeps a practitioner from idling on an unprepared patient."""
        queue = make_queue(prefer_intake_ready=True, intake_ready_window=3)
        tickets = [make_ticket(1), make_ticket(2), make_ticket(3, intake_id="i3")]
        selection = select_next(
            tickets, queue, make_instance(), {IntakeId("i3"): IntakeState.READY}
        )
        assert selection is not None
        assert selection.ticket.token_sequence == 3
        assert [t.token_sequence for t in selection.passed_over] == [1, 2]

    def test_it_never_crosses_a_priority_class(self) -> None:
        """A prepared walk-in must not jump a senior citizen."""
        queue = make_queue(prefer_intake_ready=True, intake_ready_window=3)
        tickets = [
            make_ticket(1, priority=PriorityClass.PRIORITY),
            make_ticket(2, intake_id="i2"),
        ]
        selection = select_next(
            tickets, queue, make_instance(), {IntakeId("i2"): IntakeState.READY}
        )
        assert selection is not None
        assert selection.ticket.token_sequence == 1

    def test_it_never_reaches_beyond_the_window(self) -> None:
        queue = make_queue(prefer_intake_ready=True, intake_ready_window=2)
        tickets = [make_ticket(1), make_ticket(2), make_ticket(3), make_ticket(4, intake_id="i4")]
        selection = select_next(
            tickets, queue, make_instance(), {IntakeId("i4"): IntakeState.READY}
        )
        assert selection is not None
        assert selection.ticket.token_sequence == 1

    def test_the_starvation_guard_yields_to_a_capped_ticket(self) -> None:
        """Once someone has been passed the maximum number of times, the
        preference stops applying to them — permanently, not merely this turn."""
        queue = make_queue(prefer_intake_ready=True, intake_ready_window=3, max_overtaken=2)
        tickets = [make_ticket(1, overtaken=2), make_ticket(2, intake_id="i2")]
        selection = select_next(
            tickets, queue, make_instance(), {IntakeId("i2"): IntakeState.READY}
        )
        assert selection is not None
        assert selection.ticket.token_sequence == 1

    def test_calling_increments_overtaken_on_every_ticket_passed(self) -> None:
        queue = make_queue(prefer_intake_ready=True, intake_ready_window=3)
        tickets = [make_ticket(1), make_ticket(2), make_ticket(3, intake_id="i3")]
        result = ops.call_next(
            queue,
            make_instance(),
            tickets,
            {IntakeId("i3"): IntakeState.READY},
            now=NOW,
        )
        assert result is not None
        assert {t.overtaken_count for t in result.affected_tickets} == {1}
        assert any(e.name == "queue.ticket.overtaken" for e in result.events)

    def test_a_ticket_with_no_intake_is_never_preferred(self) -> None:
        queue = make_queue(prefer_intake_ready=True)
        selection = select_next([make_ticket(1), make_ticket(2)], queue, make_instance(), {})
        assert selection is not None
        assert selection.ticket.token_sequence == 1


class TestAssignmentPolicies:
    def test_pooled_lets_any_caller_take_any_ticket(self) -> None:
        selection = select_next(
            [make_ticket(1)],
            make_queue(assignment_policy=AssignmentPolicy.POOLED_BY_DEPARTMENT),
            make_instance(),
            {},
            practitioner_id="anyone",
        )
        assert selection is not None

    def test_per_practitioner_binds_the_instance_to_one_person(self) -> None:
        queue = make_queue(assignment_policy=AssignmentPolicy.PER_PRACTITIONER)
        instance = make_instance(practitioner_id=UserId("dr-1"))
        assert select_next([make_ticket(1)], queue, instance, {}, practitioner_id="dr-1")
        assert select_next([make_ticket(1)], queue, instance, {}, practitioner_id="dr-2") is None

    def test_per_service_point_binds_to_the_room(self) -> None:
        queue = make_queue(assignment_policy=AssignmentPolicy.PER_SERVICE_POINT)
        instance = make_instance(service_point="PK-HALL")
        assert select_next([make_ticket(1)], queue, instance, {}, service_point="PK-HALL")
        assert select_next([make_ticket(1)], queue, instance, {}, service_point="OPD-9") is None


class TestPriorityPolicy:
    @pytest.mark.parametrize(
        ("attributes", "expected"),
        [
            (PatientAttributes(is_staff_referred_emergency=True), PriorityClass.EMERGENCY),
            (PatientAttributes(is_pregnant=True), PriorityClass.PRIORITY),
            (PatientAttributes(is_differently_abled=True), PriorityClass.PRIORITY),
            (PatientAttributes(age_years=72), PriorityClass.PRIORITY),
            (PatientAttributes(age_years=1), PriorityClass.PRIORITY),
            (PatientAttributes(age_years=34, has_appointment=True), PriorityClass.APPOINTMENT),
            (PatientAttributes(age_years=34), PriorityClass.WALKIN),
        ],
    )
    def test_classification(
        self, attributes: PatientAttributes, expected: PriorityClass
    ) -> None:
        assert PriorityPolicy().classify(attributes)[0] is expected

    def test_the_reason_is_recorded_for_audit(self) -> None:
        """"Why was this patient prioritised?" gets a rule, not a shrug."""
        _, reason = PriorityPolicy().classify(PatientAttributes(age_years=72))
        assert "senior citizen" in reason

    def test_the_senior_citizen_age_is_facility_configurable(self) -> None:
        policy = PriorityPolicy(senior_citizen_age=65)
        assert policy.classify(PatientAttributes(age_years=62))[0] is PriorityClass.WALKIN

    def test_a_class_the_queue_does_not_honour_is_downgraded(self) -> None:
        """A clinic that takes no appointments must not order an appointment
        ticket ahead of everyone."""
        assert (
            honoured_classes(
                (PriorityClass.EMERGENCY, PriorityClass.WALKIN), PriorityClass.APPOINTMENT
            )
            is PriorityClass.WALKIN
        )


class TestOperations:
    def test_issue_produces_a_prefixed_token_and_bumps_the_counter(self) -> None:
        result = ops.issue(
            make_queue(),
            make_instance(),
            ticket_id=TicketId("t1"),
            sequence=14,
            priority_class=PriorityClass.WALKIN,
            now=NOW,
        )
        assert result.ticket is not None
        assert result.ticket.token_number == "KC-014"
        assert result.instance is not None
        assert result.instance.counters.last_issued == 14
        assert result.instance.counters.waiting_count == 1

    def test_issue_respects_capacity(self) -> None:
        instance = make_instance(counters=QueueCounters(last_issued=5))
        with pytest.raises(ops.QueueOperationError, match="capacity"):
            ops.issue(
                make_queue(capacity=5),
                instance,
                ticket_id=TicketId("t1"),
                sequence=6,
                priority_class=PriorityClass.WALKIN,
                now=NOW,
            )

    def test_a_paused_instance_refuses_new_tokens_and_calls(self) -> None:
        paused = make_instance(status=InstanceStatus.PAUSED)
        with pytest.raises(ops.QueueOperationError, match="paused"):
            ops.call_next(make_queue(), paused, [make_ticket(1)], {}, now=NOW)

    def test_recall_reinserts_the_patient_rather_than_dropping_them(self) -> None:
        """A patient who missed a call because they were in the toilet gets more
        chances, and the transition is always an explicit recorded event."""
        called = make_ticket(1, state=QueueState.CALLED)
        result = ops.recall(make_queue(recall_after_tokens=3), make_instance(), called, now=NOW)
        assert result.ticket is not None
        assert result.ticket.state is QueueState.RECALLED
        assert result.ticket.recall_count == 1
        assert result.ticket.effective_sequence == 4

    def test_recall_becomes_no_show_only_after_the_cap(self) -> None:
        """Two more chances, then an explicit NO_SHOW. Never a silent drop."""
        policies = QueuePolicySet(recall=RecallPolicy(after_tokens=3, max_recalls=2))
        ticket = make_ticket(1, state=QueueState.CALLED)
        for expected in (1, 2):
            result = ops.recall(make_queue(), make_instance(), ticket, now=NOW, policies=policies)
            assert result.ticket is not None
            assert result.ticket.recall_count == expected
            # The patient was called again and again did not present.
            ticket = replace(result.ticket, state=QueueState.CALLED)
        final = ops.recall(make_queue(), make_instance(), ticket, now=NOW, policies=policies)
        assert final.ticket is not None
        assert final.ticket.state is QueueState.NO_SHOW

    def test_defer_preserves_priority_and_accumulated_wait(self) -> None:
        """A deferred senior citizen must not come back as a fresh walk-in."""
        ticket = make_ticket(1, priority=PriorityClass.PRIORITY, issued_at=NOW)
        later = NOW + timedelta(minutes=25)
        result = ops.defer(make_queue(), make_instance(), ticket, now=later, reason="lab test")
        assert result.ticket is not None
        assert result.ticket.priority_class is PriorityClass.PRIORITY
        assert result.ticket.wait_credit_seconds == pytest.approx(1500.0)

    def test_transfer_carries_the_intake_and_does_not_re_run_it(self) -> None:
        ticket = make_ticket(1, intake_id="i1", issued_at=NOW)
        target_queue = make_queue(queue_id=QueueId("q2"), token_prefix="ST")
        target_instance = make_instance(
            instance_id=QueueInstanceId("qi2"), queue_id=QueueId("q2")
        )
        result = ops.transfer(
            make_queue(),
            make_instance(),
            ticket,
            target_queue=target_queue,
            target_instance=target_instance,
            new_ticket_id=TicketId("t99"),
            new_sequence=7,
            now=NOW + timedelta(minutes=10),
        )
        assert result.ticket is not None
        assert result.ticket.intake_id == "i1"
        assert result.ticket.token_number == "ST-007"
        assert result.ticket.wait_credit_seconds == pytest.approx(600.0)
        assert result.affected_tickets[0].state is QueueState.TRANSFERRED

    def test_complete_folds_the_duration_into_the_rolling_mean(self) -> None:
        started = replace(make_ticket(1, state=QueueState.IN_CONSULTATION), started_at=NOW)
        result = ops.complete(
            make_queue(), make_instance(), started, now=NOW + timedelta(minutes=10)
        )
        assert result.instance is not None
        assert result.instance.counters.avg_service_seconds == pytest.approx(600.0)
        assert result.instance.counters.completed_count == 1

    def test_completing_a_ticket_that_never_started_is_rejected(self) -> None:
        with pytest.raises(ops.QueueOperationError, match="only a consultation"):
            ops.complete(make_queue(), make_instance(), make_ticket(1), now=NOW)

    def test_close_carries_unserved_tickets_forward_by_default(self) -> None:
        """No implicit disposal: the default keeps the patient in the system."""
        result = ops.close_instance(
            make_queue(), make_instance(), [make_ticket(1), make_ticket(2)], now=NOW
        )
        assert result.instance is not None
        assert result.instance.status is InstanceStatus.CLOSED
        assert {t.state for t in result.affected_tickets} == {QueueState.DEFERRED}

    def test_close_can_be_configured_to_cancel_instead(self) -> None:
        policies = QueuePolicySet(closure=ClosurePolicy(unserved=UnservedPolicy.CANCEL))
        result = ops.close_instance(
            make_queue(), make_instance(), [make_ticket(1)], now=NOW, policies=policies
        )
        assert result.affected_tickets[0].state is QueueState.CANCELLED

    def test_reassign_closure_requires_a_target(self) -> None:
        with pytest.raises(ValueError, match="reassign_to_queue_id"):
            ClosurePolicy(unserved=UnservedPolicy.REASSIGN)

    def test_pause_and_resume_round_trip(self) -> None:
        paused = ops.pause(make_instance(), now=NOW, reason="ward rounds")
        assert paused.instance is not None
        assert paused.instance.status is InstanceStatus.PAUSED
        resumed = ops.resume(paused.instance, now=NOW)
        assert resumed.instance is not None
        assert resumed.instance.status is InstanceStatus.OPEN

    def test_events_carry_no_clinical_text(self) -> None:
        """These fan out to a waiting-room display."""
        result = ops.issue(
            make_queue(),
            make_instance(),
            ticket_id=TicketId("t1"),
            sequence=1,
            priority_class=PriorityClass.WALKIN,
            now=NOW,
        )
        for event in result.events:
            assert set(event.payload) <= {"token", "priority_class", "priority_reason"}


class TestCounters:
    def test_estimated_wait_uses_the_rolling_mean_once_available(self) -> None:
        """"About 22 minutes, enough time to record your history" is what
        actually drives kiosk adoption."""
        instance = make_instance(counters=QueueCounters(avg_service_seconds=420.0))
        assert estimated_wait_minutes(4, instance) == 21

    def test_the_head_of_the_queue_waits_zero(self) -> None:
        assert estimated_wait_minutes(1, make_instance()) == 0

    def test_a_conservative_default_is_used_before_any_completion(self) -> None:
        assert estimated_wait_minutes(3, make_instance()) == 16

    def test_position_reflects_the_strict_order(self) -> None:
        tickets = [make_ticket(1), make_ticket(2, priority=PriorityClass.EMERGENCY)]
        assert position_of(tickets[1], tickets) == 1
        assert position_of(tickets[0], tickets) == 2

    def test_waiting_minutes_includes_carried_credit(self) -> None:
        ticket = replace(make_ticket(1, issued_at=NOW), wait_credit_seconds=600.0)
        assert ticket.waiting_minutes(NOW + timedelta(minutes=5)) == pytest.approx(15.0)
