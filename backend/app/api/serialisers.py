"""Domain -> DTO conversion.

One module so no router builds a response shape by hand and quietly omits a
provenance field.
"""

from __future__ import annotations

from typing import Any

from app.domain.clinical.enums import IntakeState
from app.domain.clinical.fact import ClinicalFact
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.clinical.provenance import SourceRef
from app.domain.contradictions.detector import Contradiction
from app.domain.coverage.coverage import CoverageReport, MissingField
from app.domain.queue.entities import Queue, QueueInstance
from app.domain.redflags.evaluator import RedFlagAlert
from app.domain.statemachine.engine import Complete, Step
from app.domain.summary.builder import ClinicalSummary
from app.schemas.intake import (
    AlertOut,
    AnswerSpecOut,
    CompleteOut,
    ConflictSideOut,
    ContradictionOut,
    CoverageOut,
    FactOut,
    IntakeOut,
    IntakeSnapshotOut,
    MissingFieldOut,
    ReportOut,
    SectionCoverageOut,
    SourceRefOut,
    StepOut,
    SummaryLineOut,
    SummarySectionOut,
)
from app.schemas.queue import (
    CountersOut,
    QueueInstanceOut,
    QueueOut,
    TicketOut,
)
from app.services.intake import IntakeSnapshot
from app.services.queue import TicketView


def source_ref_out(ref: SourceRef) -> SourceRefOut:
    if ref.transcript is not None:
        return SourceRefOut(
            kind="transcript",
            segment_id=str(ref.transcript.segment_id),
            start_ms=ref.transcript.start_ms,
            end_ms=ref.transcript.end_ms,
        )
    if ref.document is not None:
        bbox = ref.document.bbox
        return SourceRefOut(
            kind="document",
            document_id=str(ref.document.document_id),
            page=ref.document.page,
            bbox=(
                None
                if bbox is None
                else {"x": bbox.x, "y": bbox.y, "width": bbox.width, "height": bbox.height}
            ),
        )
    return SourceRefOut(kind="actor", entered_by=ref.entered_by)


def fact_out(fact: ClinicalFact) -> FactOut:
    return FactOut(
        fact_id=str(fact.fact_id),
        concept=fact.concept.concept_id,
        display=fact.concept.display,
        section=fact.section,
        status=fact.status,
        certainty=fact.certainty,
        temporality=fact.temporality,
        value=fact.rendered_value(),
        original_expression=fact.original_expression,
        original_language=fact.original_language,
        source_type=fact.source_type,
        source_ref=source_ref_out(fact.source_ref),
        confidence=fact.confidence,
        reported_by=fact.reported_by,
        patient_confirmed=fact.patient_confirmed,
        physician_verified=fact.physician_verified,
        recorded_at=fact.recorded_at.isoformat(),
        supersedes=str(fact.supersedes) if fact.supersedes else None,
    )


def step_out(step: Step) -> StepOut:
    return StepOut(
        concept=step.concept,
        question=step.question,
        language=step.language,
        answer=AnswerSpecOut(
            type=step.answer.shape,
            options=list(step.answer.options),
            unit=step.answer.unit,
            min=step.answer.minimum,
            max=step.answer.maximum,
        ),
        section=step.section,
        required=step.required,
        skippable=step.skippable,
        origin=step.origin.value,
        source_pathway=step.source_pathway,
        selection_reason=step.selection_reason,
        touch_options=list(step.touch_options),
        confirming_value=step.confirming_value,
        prompts=dict(step.prompts),
    )


def complete_out(complete: Complete) -> CompleteOut:
    return CompleteOut(
        reason=complete.reason,
        required_total=complete.required_total,
        required_settled=complete.required_settled,
        optional_asked=complete.optional_asked,
    )


def next_step_out(value: Step | Complete) -> StepOut | CompleteOut:
    return step_out(value) if isinstance(value, Step) else complete_out(value)


def missing_out(missing: MissingField) -> MissingFieldOut:
    return MissingFieldOut(
        concept=missing.concept,
        section=missing.section,
        required=missing.required,
        reason=missing.reason,
        description=missing.describe(),
    )


def coverage_out(coverage: CoverageReport) -> CoverageOut:
    return CoverageOut(
        percentage=coverage.percentage,
        is_complete=coverage.is_complete,
        required_total=coverage.required_total,
        required_captured=coverage.required_captured,
        required_not_applicable=coverage.required_not_applicable,
        required_declined=coverage.required_declined,
        optional_captured=coverage.optional_captured,
        optional_total=coverage.optional_total,
        sections=[
            SectionCoverageOut(
                section=s.section,
                required=s.required,
                captured=s.captured,
                not_applicable=s.not_applicable,
                unanswered=s.unanswered,
                declined=s.declined,
                percentage=s.percentage,
                is_complete=s.is_complete,
                missing=[missing_out(m) for m in s.missing],
            )
            for s in coverage.sections
        ],
        missing_required=[missing_out(m) for m in coverage.missing_required()],
    )


def alert_out(alert: RedFlagAlert) -> AlertOut:
    return AlertOut(
        alert_id=str(alert.alert_id) if alert.alert_id else None,
        rule_id=alert.rule_id,
        severity=alert.severity,
        label=alert.label,
        patient_safe_label=alert.patient_safe_label,
        clinical_source=alert.clinical_source,
        criteria_description=alert.criteria_description,
        supporting_facts=[str(f) for f in alert.supporting_facts],
        notify=alert.action.notify,
        priority_hint=alert.action.priority_hint,
        raised_at=alert.raised_at.isoformat() if alert.raised_at else None,
        acknowledged_by=str(alert.acknowledged_by) if alert.acknowledged_by else None,
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        dismissed_by=str(alert.dismissed_by) if alert.dismissed_by else None,
        dismissal_reason=alert.dismissal_reason,
        is_open=alert.is_open,
    )


def contradiction_out(conflict: Contradiction) -> ContradictionOut:
    def side(value: Any) -> ConflictSideOut | None:
        if value is None:
            return None
        return ConflictSideOut(
            fact_id=value.fact_id,
            statement=value.statement,
            source_type=value.source_type,
            source_label=value.source_label,
            confidence=value.confidence,
            recorded_at_label=value.recorded_at_label,
            patient_confirmed=value.patient_confirmed,
        )

    from_record = side(conflict.from_record)
    assert from_record is not None
    return ContradictionOut(
        concept=conflict.concept,
        kind=conflict.kind.value,
        reported_today=side(conflict.reported_today),
        from_record=from_record,
        resolution=conflict.resolution,
        rendered=conflict.render(),
    )


def intake_out(state: PatientIntakeState) -> IntakeOut:
    return IntakeOut(
        intake_id=str(state.intake_id),
        state=state.state,
        revision=state.revision,
        language=state.language,
        reporter=state.reporter,
        active_pathway=state.active_pathway,
        ayurveda_enabled=state.ayurveda_enabled,
        patient_id=str(state.patient_id) if state.patient_id else None,
        consent_artefact_id=state.consent_artefact_id,
        declined=sorted(state.declined),
        facts=[fact_out(f) for f in state.current()],
        documents=[
            {
                "document_id": d.document_id,
                "kind": d.kind,
                "uploaded_at": d.uploaded_at.isoformat(),
                "processed": d.processed,
                "page_count": d.page_count,
                "low_confidence": d.low_confidence,
            }
            for d in state.documents
        ],
    )


def snapshot_out(snapshot: IntakeSnapshot) -> IntakeSnapshotOut:
    return IntakeSnapshotOut(
        intake=intake_out(snapshot.state),
        next_step=next_step_out(snapshot.next_step),
        coverage=coverage_out(snapshot.coverage),
        alerts=[alert_out(a) for a in snapshot.alerts],
        newly_raised=[alert_out(a) for a in snapshot.newly_raised],
        contradictions=[contradiction_out(c) for c in snapshot.contradictions],
    )


def report_out(summary: ClinicalSummary) -> ReportOut:
    return ReportOut(
        intake_id=summary.intake_id,
        coverage_percentage=summary.coverage_percentage,
        sections=[
            SummarySectionOut(
                section=s.section,
                title=s.title,
                lines=[
                    SummaryLineOut(
                        text=line.text,
                        fact_ids=[str(f) for f in line.fact_ids],
                        original_expression=line.original_expression,
                        original_language=line.original_language,
                    )
                    for line in s.lines
                ],
            )
            for s in summary.sections
        ],
        unresolved=[
            SummaryLineOut(text=line.text, fact_ids=[str(f) for f in line.fact_ids])
            for line in summary.unresolved
        ],
        conflicts=[contradiction_out(c) for c in summary.conflicts],
        alerts=[alert_out(a) for a in summary.alerts],
        physician_verified=summary.physician_verified,
        rendered_text=summary.render_text(),
    )


def queue_out(queue: Queue) -> QueueOut:
    return QueueOut(
        queue_id=str(queue.queue_id),
        name=queue.name,
        department_code=queue.department_code,
        service_point=queue.service_point,
        assignment_policy=queue.assignment_policy,
        token_prefix=queue.token_prefix,
        capacity=queue.capacity,
        session=queue.session,
        prefer_intake_ready=queue.prefer_intake_ready,
        intake_ready_window=queue.intake_ready_window,
        max_overtaken=queue.max_overtaken,
        unserved_policy=queue.unserved_policy,
        mode=queue.mode.value,
    )


def instance_out(instance: QueueInstance) -> QueueInstanceOut:
    return QueueInstanceOut(
        instance_id=str(instance.instance_id),
        queue_id=str(instance.queue_id),
        service_date=instance.service_date,
        session=instance.session,
        status=instance.status,
        practitioner_id=str(instance.practitioner_id) if instance.practitioner_id else None,
        service_point=instance.service_point,
        counters=CountersOut(
            last_issued=instance.counters.last_issued,
            now_serving=instance.counters.now_serving,
            waiting_count=instance.counters.waiting_count,
            completed_count=instance.counters.completed_count,
            no_show_count=instance.counters.no_show_count,
            avg_service_seconds=instance.counters.avg_service_seconds,
        ),
    )


def ticket_out(view: TicketView, *, intake_state: IntakeState | None = None) -> TicketOut:
    """Serialise a ticket.

    `intake_state` is passed in rather than read off the ticket, because the
    ticket does not carry it — the two state machines are separate and stay that
    way right up to the wire format.
    """
    ticket = view.ticket
    return TicketOut(
        ticket_id=str(ticket.ticket_id),
        queue_id=str(ticket.queue_id),
        instance_id=str(ticket.instance_id),
        token_number=ticket.token_number,
        token_sequence=ticket.token_sequence,
        priority_class=ticket.priority_class,
        queue_state=ticket.state,
        intake_state=intake_state,
        patient_id=str(ticket.patient_id) if ticket.patient_id else None,
        intake_id=str(ticket.intake_id) if ticket.intake_id else None,
        issued_at=ticket.issued_at,
        called_at=ticket.called_at,
        started_at=ticket.started_at,
        completed_at=ticket.completed_at,
        recall_count=ticket.recall_count,
        overtaken_count=ticket.overtaken_count,
        position=view.position,
        estimated_wait_minutes=view.estimated_wait_minutes,
        waiting_minutes=view.waiting_minutes,
        escalation_alert_id=(
            str(ticket.escalation.alert_id) if ticket.escalation else None
        ),
    )
