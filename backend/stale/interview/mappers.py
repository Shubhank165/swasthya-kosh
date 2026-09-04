"""ORM row <-> domain entity translation.

Kept in one module so the domain never imports SQLAlchemy and the repositories
never construct domain objects ad hoc. Every field survives the round trip;
`tests/unit/test_mappers.py` proves it, because a provenance field silently lost
in translation would be indistinguishable from one that was never captured.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.domain.clinical.enums import (
    Certainty,
    FactStatus,
    IntakeState,
    ReporterRole,
    Section,
    Severity,
    SourceType,
    Temporality,
)
from app.domain.clinical.fact import ClinicalFact
from app.domain.clinical.patient_state import DocumentRecord, PatientIntakeState
from app.domain.clinical.provenance import (
    AlertId,
    BooleanValue,
    BoundingBox,
    CodedValue,
    ConceptRef,
    DateValue,
    DocumentId,
    Duration,
    FactId,
    FactValue,
    IntakeId,
    PatientId,
    Quantity,
    QueueId,
    QueueInstanceId,
    ScaleValue,
    SegmentId,
    SourceRef,
    TextValue,
    TicketId,
    UserId,
)
from app.domain.queue.entities import (
    AssignmentPolicy,
    Department,
    EscalationRecord,
    InstanceStatus,
    PriorityClass,
    Queue,
    QueueCounters,
    QueueInstance,
    QueueMode,
    QueueState,
    SessionName,
    Ticket,
    UnservedPolicy,
)
from app.domain.redflags.evaluator import RedFlagAlert
from app.domain.redflags.rules import RedFlagAction
from app.models.clinical import (
    ClinicalFactRecord,
    DocumentRecordRow,
    IntakeRecord,
    RedFlagAlertRecord,
)
from app.models.queue import (
    DepartmentRecord,
    QueueInstanceRecord,
    QueueRecord,
    TicketRecord,
)

# --- fact values -------------------------------------------------------------


def value_to_json(value: FactValue | None) -> dict[str, Any] | None:
    """Serialise a typed value, tagged so it round-trips to the same type.

    A `Duration` of two weeks must not come back as a `Quantity` of 2: the unit
    and the type together are what make it clinically readable.
    """
    if value is None:
        return None
    if isinstance(value, Quantity):
        return {"kind": "quantity", "magnitude": value.magnitude, "unit": value.unit}
    if isinstance(value, Duration):
        return {"kind": "duration", "magnitude": value.magnitude, "unit": value.unit}
    if isinstance(value, CodedValue):
        return {
            "kind": "coded",
            "code": value.code,
            "system": value.system,
            "display": value.display,
        }
    if isinstance(value, TextValue):
        return {"kind": "text", "text": value.text}
    if isinstance(value, BooleanValue):
        return {"kind": "boolean", "value": value.value}
    if isinstance(value, DateValue):
        return {"kind": "date", "value": value.value.isoformat(), "precision": value.precision}
    return {
        "kind": "scale",
        "value": value.value,
        "minimum": value.minimum,
        "maximum": value.maximum,
    }


def value_from_json(raw: dict[str, Any] | None) -> FactValue | None:
    if raw is None:
        return None
    kind = raw.get("kind")
    if kind == "quantity":
        return Quantity(float(raw["magnitude"]), str(raw["unit"]))
    if kind == "duration":
        return Duration(float(raw["magnitude"]), str(raw["unit"]))
    if kind == "coded":
        return CodedValue(str(raw["code"]), raw.get("system"), raw.get("display"))
    if kind == "text":
        return TextValue(str(raw["text"]))
    if kind == "boolean":
        return BooleanValue(bool(raw["value"]))
    if kind == "date":
        return DateValue(date.fromisoformat(str(raw["value"])), str(raw.get("precision", "day")))
    if kind == "scale":
        return ScaleValue(float(raw["value"]), float(raw["minimum"]), float(raw["maximum"]))
    raise ValueError(f"unknown fact value kind: {kind!r}")


def source_ref_to_json(ref: SourceRef) -> dict[str, Any]:
    if ref.transcript is not None:
        return {
            "kind": "transcript",
            "segment_id": str(ref.transcript.segment_id),
            "start_ms": ref.transcript.start_ms,
            "end_ms": ref.transcript.end_ms,
        }
    if ref.document is not None:
        bbox = ref.document.bbox
        return {
            "kind": "document",
            "document_id": str(ref.document.document_id),
            "page": ref.document.page,
            "bbox": (
                None
                if bbox is None
                else {"x": bbox.x, "y": bbox.y, "width": bbox.width, "height": bbox.height}
            ),
        }
    return {"kind": "actor", "entered_by": ref.entered_by}


def source_ref_from_json(raw: dict[str, Any]) -> SourceRef:
    kind = raw.get("kind")
    if kind == "transcript":
        return SourceRef.from_transcript(
            SegmentId(str(raw["segment_id"])), int(raw["start_ms"]), int(raw["end_ms"])
        )
    if kind == "document":
        bbox_raw = raw.get("bbox")
        bbox = (
            None
            if bbox_raw is None
            else BoundingBox(
                float(bbox_raw["x"]),
                float(bbox_raw["y"]),
                float(bbox_raw["width"]),
                float(bbox_raw["height"]),
            )
        )
        return SourceRef.from_document(DocumentId(str(raw["document_id"])), int(raw["page"]), bbox)
    return SourceRef.from_actor(str(raw["entered_by"]))


# --- facts -------------------------------------------------------------------


def fact_to_row(
    fact: ClinicalFact, *, intake_id: str, seq: int, record_channel: bool = False
) -> ClinicalFactRecord:
    return ClinicalFactRecord(
        id=str(fact.fact_id),
        seq=seq,
        intake_id=intake_id,
        concept_id=fact.concept.concept_id,
        concept_system=fact.concept.system,
        concept_code=fact.concept.code,
        concept_display=fact.concept.display,
        section=fact.section.value,
        status=fact.status.value,
        certainty=fact.certainty.value,
        temporality=fact.temporality.value,
        value=value_to_json(fact.value),
        original_expression=fact.original_expression,
        original_language=fact.original_language,
        source_type=fact.source_type.value,
        source_ref=source_ref_to_json(fact.source_ref),
        confidence=fact.confidence,
        reported_by=fact.reported_by.value,
        patient_confirmed=fact.patient_confirmed,
        physician_verified=fact.physician_verified,
        recorded_at=fact.recorded_at,
        supersedes=str(fact.supersedes) if fact.supersedes else None,
        note=fact.note,
        record_channel=record_channel,
    )


def fact_from_row(row: ClinicalFactRecord) -> ClinicalFact:
    return ClinicalFact(
        fact_id=FactId(row.id),
        concept=ConceptRef(
            row.concept_id,
            system=row.concept_system,
            code=row.concept_code,
            display=row.concept_display,
        ),
        status=FactStatus(row.status),
        certainty=Certainty(row.certainty),
        temporality=Temporality(row.temporality),
        source_type=SourceType(row.source_type),
        source_ref=source_ref_from_json(row.source_ref),
        confidence=row.confidence,
        reported_by=ReporterRole(row.reported_by),
        recorded_at=row.recorded_at,
        section=Section(row.section),
        value=value_from_json(row.value),
        original_expression=row.original_expression,
        original_language=row.original_language,
        patient_confirmed=row.patient_confirmed,
        physician_verified=row.physician_verified,
        supersedes=FactId(row.supersedes) if row.supersedes else None,
        note=row.note,
    )


# --- intake ------------------------------------------------------------------


def intake_from_rows(
    row: IntakeRecord,
    facts: list[ClinicalFactRecord],
    documents: list[DocumentRecordRow],
) -> PatientIntakeState:
    ordered = sorted(facts, key=lambda f: f.seq)
    return PatientIntakeState(
        intake_id=IntakeId(row.id),
        facts=tuple(fact_from_row(f) for f in ordered if not f.record_channel),
        record_facts=tuple(fact_from_row(f) for f in ordered if f.record_channel),
        state=IntakeState(row.state),
        revision=row.revision,
        patient_id=PatientId(row.patient_id) if row.patient_id else None,
        language=row.language,
        reporter=ReporterRole(row.reporter_role),
        active_pathway=row.active_pathway,
        active_ros_groups=tuple(row.active_ros_groups or ()),
        ayurveda_enabled=row.ayurveda_enabled,
        documents=tuple(
            DocumentRecord(
                document_id=d.id,
                kind=d.kind,
                uploaded_at=d.uploaded_at,
                processed=d.processed,
                page_count=d.page_count,
                low_confidence=d.low_confidence,
            )
            for d in documents
        ),
        declined=frozenset(row.declined_concepts or ()),
        consent_artefact_id=row.consent_artefact_id,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def apply_intake_to_row(row: IntakeRecord, state: PatientIntakeState) -> None:
    """Copy session metadata onto the row. Facts are written separately, because
    they are appended rather than synchronised."""
    row.state = state.state.value
    row.revision = state.revision
    row.language = state.language
    row.reporter_role = state.reporter.value
    row.active_pathway = state.active_pathway
    row.active_ros_groups = list(state.active_ros_groups)
    row.ayurveda_enabled = state.ayurveda_enabled
    row.declined_concepts = sorted(state.declined)
    row.consent_artefact_id = state.consent_artefact_id
    row.patient_id = str(state.patient_id) if state.patient_id else None
    row.started_at = state.started_at
    row.completed_at = state.completed_at


# --- queue -------------------------------------------------------------------


def department_from_row(row: DepartmentRecord) -> Department:
    return Department(code=row.code, name=row.name, facility=row.facility)


def queue_from_row(row: QueueRecord) -> Queue:
    return Queue(
        queue_id=QueueId(row.id),
        name=row.name,
        department_code=row.department_code,
        service_point=row.service_point,
        assignment_policy=AssignmentPolicy(row.assignment_policy),
        token_prefix=row.token_prefix,
        capacity=row.capacity,
        schedule_days=tuple(row.schedule_days or ()),
        session=SessionName(row.session),
        priority_classes=tuple(PriorityClass(p) for p in (row.priority_classes or []))
        or (
            PriorityClass.EMERGENCY,
            PriorityClass.PRIORITY,
            PriorityClass.APPOINTMENT,
            PriorityClass.WALKIN,
        ),
        prefer_intake_ready=row.prefer_intake_ready,
        intake_ready_window=row.intake_ready_window,
        max_overtaken=row.max_overtaken,
        recall_after_tokens=row.recall_after_tokens,
        max_recalls=row.max_recalls,
        unserved_policy=UnservedPolicy(row.unserved_policy),
        mode=QueueMode(row.mode),
    )


def instance_from_row(row: QueueInstanceRecord) -> QueueInstance:
    return QueueInstance(
        instance_id=QueueInstanceId(row.id),
        queue_id=QueueId(row.queue_id),
        service_date=row.service_date,
        session=SessionName(row.session),
        status=InstanceStatus(row.status),
        practitioner_id=UserId(row.practitioner_id) if row.practitioner_id else None,
        service_point=row.service_point,
        counters=QueueCounters(
            last_issued=row.last_issued,
            now_serving=row.now_serving,
            waiting_count=row.waiting_count,
            completed_count=row.completed_count,
            no_show_count=row.no_show_count,
            avg_service_seconds=row.avg_service_seconds,
            served_sample=row.served_sample,
        ),
        opened_at=row.opened_at,
        paused_at=row.paused_at,
        closed_at=row.closed_at,
        merged_into=QueueInstanceId(row.merged_into) if row.merged_into else None,
    )


def apply_instance_to_row(row: QueueInstanceRecord, instance: QueueInstance) -> None:
    row.status = instance.status.value
    row.practitioner_id = str(instance.practitioner_id) if instance.practitioner_id else None
    row.service_point = instance.service_point
    row.last_issued = instance.counters.last_issued
    row.now_serving = instance.counters.now_serving
    row.waiting_count = instance.counters.waiting_count
    row.completed_count = instance.counters.completed_count
    row.no_show_count = instance.counters.no_show_count
    row.avg_service_seconds = instance.counters.avg_service_seconds
    row.served_sample = instance.counters.served_sample
    row.opened_at = instance.opened_at
    row.paused_at = instance.paused_at
    row.closed_at = instance.closed_at
    row.merged_into = str(instance.merged_into) if instance.merged_into else None


def ticket_from_row(row: TicketRecord) -> Ticket:
    escalation = (
        EscalationRecord(
            alert_id=AlertId(row.escalation_alert_id),
            acknowledged_by=UserId(row.escalation_acknowledged_by or ""),
            escalated_by=UserId(row.escalation_escalated_by or ""),
            escalated_at=row.escalation_at,
            reason=row.escalation_reason,
        )
        if row.escalation_alert_id and row.escalation_at
        else None
    )
    return Ticket(
        ticket_id=TicketId(row.id),
        queue_id=QueueId(row.queue_id),
        instance_id=QueueInstanceId(row.instance_id),
        token_number=row.token_number,
        token_sequence=row.token_sequence,
        priority_class=PriorityClass(row.priority_class),
        state=QueueState(row.state),
        issued_at=row.issued_at,
        patient_id=PatientId(row.patient_id) if row.patient_id else None,
        intake_id=IntakeId(row.intake_id) if row.intake_id else None,
        appointment_slot_time=row.appointment_slot_time,
        called_at=row.called_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        recall_count=row.recall_count,
        overtaken_count=row.overtaken_count,
        escalation=escalation,
        wait_credit_seconds=row.wait_credit_seconds,
        recall_sequence=row.recall_sequence,
        transferred_from=QueueId(row.transferred_from) if row.transferred_from else None,
        transferred_to=QueueId(row.transferred_to) if row.transferred_to else None,
        cancelled_reason=row.cancelled_reason,
        deferred_at=row.deferred_at,
    )


def ticket_to_row(ticket: Ticket) -> TicketRecord:
    row = TicketRecord(
        id=str(ticket.ticket_id),
        queue_id=str(ticket.queue_id),
        instance_id=str(ticket.instance_id),
        token_number=ticket.token_number,
        token_sequence=ticket.token_sequence,
        priority_class=ticket.priority_class.value,
        state=ticket.state.value,
        issued_at=ticket.issued_at,
    )
    apply_ticket_to_row(row, ticket)
    return row


def apply_ticket_to_row(row: TicketRecord, ticket: Ticket) -> None:
    row.state = ticket.state.value
    row.priority_class = ticket.priority_class.value
    row.token_number = ticket.token_number
    row.token_sequence = ticket.token_sequence
    row.recall_sequence = ticket.recall_sequence
    row.patient_id = str(ticket.patient_id) if ticket.patient_id else None
    row.intake_id = str(ticket.intake_id) if ticket.intake_id else None
    row.appointment_slot_time = ticket.appointment_slot_time
    row.called_at = ticket.called_at
    row.started_at = ticket.started_at
    row.completed_at = ticket.completed_at
    row.deferred_at = ticket.deferred_at
    row.recall_count = ticket.recall_count
    row.overtaken_count = ticket.overtaken_count
    row.wait_credit_seconds = ticket.wait_credit_seconds
    row.transferred_from = str(ticket.transferred_from) if ticket.transferred_from else None
    row.transferred_to = str(ticket.transferred_to) if ticket.transferred_to else None
    row.cancelled_reason = ticket.cancelled_reason
    if ticket.escalation is not None:
        row.escalation_alert_id = str(ticket.escalation.alert_id)
        row.escalation_acknowledged_by = str(ticket.escalation.acknowledged_by)
        row.escalation_escalated_by = str(ticket.escalation.escalated_by)
        row.escalation_at = ticket.escalation.escalated_at
        row.escalation_reason = ticket.escalation.reason


# --- alerts ------------------------------------------------------------------


def alert_from_row(row: RedFlagAlertRecord) -> RedFlagAlert:
    return RedFlagAlert(
        rule_id=row.rule_id,
        severity=Severity(row.severity),
        label=row.label,
        action=RedFlagAction(notify=row.notify, priority_hint=row.priority_hint),
        clinical_source=row.clinical_source,
        supporting_facts=tuple(FactId(f) for f in (row.supporting_fact_ids or [])),
        criteria_description=row.criteria_description,
        rule_version=row.rule_version,
        alert_id=AlertId(row.id),
        raised_at=row.raised_at,
        acknowledged_by=UserId(row.acknowledged_by) if row.acknowledged_by else None,
        acknowledged_at=row.acknowledged_at,
        dismissed_by=UserId(row.dismissed_by) if row.dismissed_by else None,
        dismissed_at=row.dismissed_at,
        dismissal_reason=row.dismissal_reason,
    )


def alert_to_row(alert: RedFlagAlert, *, intake_id: str) -> RedFlagAlertRecord:
    if alert.alert_id is None or alert.raised_at is None:
        raise ValueError("an alert must be given an id and a raised_at before persistence")
    return RedFlagAlertRecord(
        id=str(alert.alert_id),
        intake_id=intake_id,
        rule_id=alert.rule_id,
        rule_version=alert.rule_version,
        severity=alert.severity.value,
        label=alert.label,
        clinical_source=alert.clinical_source,
        criteria_description=alert.criteria_description,
        supporting_fact_ids=[str(f) for f in alert.supporting_facts],
        notify=alert.action.notify,
        priority_hint=alert.action.priority_hint,
        raised_at=alert.raised_at,
        acknowledged_by=str(alert.acknowledged_by) if alert.acknowledged_by else None,
        acknowledged_at=alert.acknowledged_at,
        dismissed_by=str(alert.dismissed_by) if alert.dismissed_by else None,
        dismissed_at=alert.dismissed_at,
        dismissal_reason=alert.dismissal_reason,
    )
