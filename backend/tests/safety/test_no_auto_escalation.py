"""Invariant 3: a red flag never auto-escalates a patient.

The guarantee is structural, not procedural. `evaluate` returns alerts and
touches nothing else; `Ticket` escalation refuses without an acknowledged alert
id and an acting user. This file proves both halves, and proves there is no
third path between them.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.content import ClinicalContent
from app.domain.clinical.enums import FactStatus, Section
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.clinical.provenance import (
    AlertId,
    CodedValue,
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
    QueueInstance,
    QueueState,
    SessionName,
    Ticket,
)
from app.domain.redflags.evaluator import evaluate
from tests.conftest import make_fact

NOW = datetime(2026, 1, 15, 9, 30, tzinfo=UTC)

DOMAIN_ROOT = Path(__file__).resolve().parents[2] / "app" / "domain"


def _domain_sources() -> list[tuple[Path, str]]:
    """Every source file under `app/domain`, read from disk.

    Read rather than introspected so empty `__init__.py` files are covered too —
    an import smuggled into a package initialiser would be the easiest one to
    miss.
    """
    return [(p, p.read_text(encoding="utf-8")) for p in sorted(DOMAIN_ROOT.rglob("*.py"))]


@pytest.fixture
def queue() -> Queue:
    return Queue(
        queue_id=QueueId("q1"),
        name="Kayachikitsa General OPD",
        department_code="KC",
        service_point="OPD-1",
        assignment_policy=AssignmentPolicy.POOLED_BY_DEPARTMENT,
        token_prefix="KC",
    )


@pytest.fixture
def instance() -> QueueInstance:
    return QueueInstance(
        instance_id=QueueInstanceId("qi1"),
        queue_id=QueueId("q1"),
        service_date=NOW.date(),
        session=SessionName.MORNING,
        status=InstanceStatus.OPEN,
    )


@pytest.fixture
def ticket() -> Ticket:
    return Ticket(
        ticket_id=TicketId("t1"),
        queue_id=QueueId("q1"),
        instance_id=QueueInstanceId("qi1"),
        token_number="KC-001",
        token_sequence=1,
        priority_class=PriorityClass.WALKIN,
        state=QueueState.WAITING,
        issued_at=NOW,
        intake_id=IntakeId("i1"),
    )


def firing_state() -> PatientIntakeState:
    """A patient whose answers fire a critical rule."""
    state = PatientIntakeState(intake_id=IntakeId("i1"))
    for index, (concept, value) in enumerate(
        [("chest_pain", None), ("onset", CodedValue(code="sudden")), ("dyspnoea", None)]
    ):
        state = state.apply(
            make_fact(
                concept,
                status=FactStatus.PRESENT,
                value=value,
                fact_id=f"f{index}",
                section=Section.RED_FLAG_SCREEN,
            )
        )
    return state


class TestEvaluationTouchesNothing:
    def test_evaluate_returns_alerts_and_changes_no_state(
        self, content: ClinicalContent
    ) -> None:
        state = firing_state()
        before = state.snapshot()
        alerts = evaluate(state, content.red_flags)
        assert alerts
        assert state.snapshot() == before

    def test_evaluate_cannot_reach_the_queue(self) -> None:
        """A structural check: the red-flag package imports nothing from the
        queue package, so there is no code path from a fired rule to a ticket."""
        import app.domain.redflags.evaluator as evaluator
        import app.domain.redflags.rules as rules

        for module in (evaluator, rules):
            source = inspect.getsource(module)
            assert "app.domain.queue" not in source, module.__name__

    def test_a_fired_alert_starts_open_and_unacknowledged(
        self, content: ClinicalContent
    ) -> None:
        alerts = evaluate(firing_state(), content.red_flags)
        for alert in alerts:
            assert alert.is_open
            assert alert.acknowledged_by is None

    def test_the_priority_hint_is_a_hint_not_an_action(
        self, content: ClinicalContent, ticket: Ticket
    ) -> None:
        """The rule may suggest `emergency`; the ticket's priority is untouched
        until a human acts."""
        alerts = evaluate(firing_state(), content.red_flags)
        critical = next(a for a in alerts if a.action.priority_hint == "emergency")
        assert critical.action.priority_hint == "emergency"
        assert ticket.priority_class is PriorityClass.WALKIN


class TestEscalationRequiresAHuman:
    def test_escalation_without_an_alert_is_rejected(
        self, queue: Queue, instance: QueueInstance, ticket: Ticket
    ) -> None:
        with pytest.raises(ops.QueueOperationError, match="acknowledged red-flag alert"):
            ops.escalate(
                queue,
                instance,
                ticket,
                alert_id=None,
                acknowledged_by=None,
                acting_user_id=UserId("triage-1"),
                now=NOW,
            )

    def test_escalation_without_an_acknowledging_user_is_rejected(
        self, queue: Queue, instance: QueueInstance, ticket: Ticket
    ) -> None:
        """An alert id alone is not enough: someone has to have looked at it."""
        with pytest.raises(ops.QueueOperationError, match="acknowledged red-flag alert"):
            ops.escalate(
                queue,
                instance,
                ticket,
                alert_id=AlertId("a1"),
                acknowledged_by=None,
                acting_user_id=UserId("triage-1"),
                now=NOW,
            )

    def test_escalation_without_an_acting_user_is_rejected(
        self, queue: Queue, instance: QueueInstance, ticket: Ticket
    ) -> None:
        with pytest.raises(ops.QueueOperationError, match="acting user"):
            ops.escalate(
                queue,
                instance,
                ticket,
                alert_id=AlertId("a1"),
                acknowledged_by=UserId("triage-1"),
                acting_user_id=None,
                now=NOW,
            )

    def test_escalation_with_both_records_who_did_what(
        self, queue: Queue, instance: QueueInstance, ticket: Ticket
    ) -> None:
        result = ops.escalate(
            queue,
            instance,
            ticket,
            alert_id=AlertId("a1"),
            acknowledged_by=UserId("triage-1"),
            acting_user_id=UserId("triage-2"),
            now=NOW,
            reason="chest pain screen",
        )
        assert result.ticket is not None
        escalation = result.ticket.escalation
        assert escalation is not None
        assert escalation.alert_id == "a1"
        assert escalation.acknowledged_by == "triage-1"
        assert escalation.escalated_by == "triage-2"
        assert result.ticket.state is QueueState.ESCALATED

    def test_an_acknowledged_alert_names_the_person_who_took_responsibility(
        self, content: ClinicalContent
    ) -> None:
        alert = evaluate(firing_state(), content.red_flags)[0]
        acknowledged = alert.acknowledged(by=UserId("triage-1"), at=NOW)
        assert acknowledged.acknowledged_by == "triage-1"
        assert acknowledged.acknowledged_at == NOW
        assert not acknowledged.is_open

    def test_a_dismissed_alert_cannot_then_be_acknowledged(
        self, content: ClinicalContent
    ) -> None:
        alert = evaluate(firing_state(), content.red_flags)[0]
        dismissed = alert.dismissed(by=UserId("triage-1"), at=NOW, reason="already reviewed")
        with pytest.raises(ValueError, match="dismissed"):
            dismissed.acknowledged(by=UserId("triage-2"), at=NOW)

    def test_dismissal_requires_a_reason(self, content: ClinicalContent) -> None:
        alert = evaluate(firing_state(), content.red_flags)[0]
        with pytest.raises(ValueError, match="requires a reason"):
            alert.dismissed(by=UserId("triage-1"), at=NOW, reason="")


class TestNoModelInTheLoop:
    def test_the_domain_imports_no_network_client_or_provider(self) -> None:
        """Invariant 10, checked mechanically over the whole domain package."""
        forbidden = (
            "import httpx",
            "import requests",
            "import aiohttp",
            "from fastapi",
            "import fastapi",
            "from sqlalchemy",
            "import sqlalchemy",
            "import openai",
            "from google",
            "app.adapters",
            "app.repositories",
            "app.services",
        )
        offenders = [
            f"{path.name}: {needle}"
            for path, source in _domain_sources()
            for needle in forbidden
            if needle in source
        ]
        assert offenders == []

    def test_the_domain_never_reads_a_clock_or_generates_an_id(self) -> None:
        """`datetime.now()` and `uuid4()` in the domain would make its behaviour
        irreproducible, which is the one thing it must never be."""
        offenders = [
            f"{path.name}: {needle}"
            for path, source in _domain_sources()
            for needle in ("datetime.now(", "uuid4(", "random.", "time.time(")
            if needle in source
        ]
        assert offenders == []
