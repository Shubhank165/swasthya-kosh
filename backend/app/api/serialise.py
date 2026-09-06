"""Domain objects to API models.

One place, so a field that must reach the dashboard cannot be dropped by one
router and included by another — and so the `demo` flag is attached in exactly
one function rather than remembered at fourteen call sites.
"""

from __future__ import annotations

from app.domain.record import CanonicalRecord, Fact
from app.domain.report.builder import FieldLabels
from app.domain.report.model import ReportBundle
from app.domain.worklist import Worklist
from app.schemas.api import (
    ContradictionOut,
    DocumentOut,
    FactOut,
    IntakeOut,
    RedFlagOut,
    ReportOut,
    WorklistEntryOut,
    WorklistOut,
)


def fact_out(fact: Fact, *, labels: FieldLabels) -> FactOut:
    return FactOut(
        fact_id=fact.fact_id,
        field_id=fact.field_id,
        label=labels(fact.field_id),
        status=fact.status.value,
        value=fact.value.model_dump(mode="json") if fact.value is not None else None,
        rendered=fact.rendered_value(),
        original_text=fact.original_text,
        language=fact.language,
        certainty=fact.certainty.value,
        channel=fact.channel.value,
        section=fact.section.value,
        confidence=fact.confidence,
        physician_verified=fact.physician_verified,
        physician_action=(
            fact.physician_action.value if fact.physician_action is not None else None
        ),
        repaired=fact.repaired,
        needs_verification=fact.needs_verification,
        carried_forward=(
            fact.carried_forward.model_dump(mode="json")
            if fact.carried_forward is not None
            else None
        ),
        source=fact.source.model_dump(mode="json"),
        recorded_at=fact.recorded_at,
    )


def intake_out(
    record: CanonicalRecord,
    *,
    labels: FieldLabels,
    demo: bool = False,
    urls: dict[str, str] | None = None,
) -> IntakeOut:
    """The whole record.

    `live_facts()` rather than `facts`: superseded revisions stay in the
    database and in the audit trail, but a dashboard showing four revisions of
    the same answer is a dashboard nobody can read. The revision chain is
    reachable through the evidence endpoint.
    """
    return IntakeOut(
        intake_id=str(record.intake_id),
        hospital_id=record.hospital_id,
        status=record.status.value,
        language=record.language,
        department_code=record.department_code,
        patient_ref={
            "type": record.patient_ref.type.value,
            "value": record.patient_ref.value,
        },
        facts=[fact_out(f, labels=labels) for f in record.live_facts()],
        red_flags=[
            RedFlagOut(
                rule_id=event.rule_id,
                severity=event.severity,
                label=event.label,
                fired_at_turn=event.fired_at_turn,
                criteria_met=list(event.criteria_met),
                acknowledged_by=event.acknowledged_by,
                acknowledged_at=event.acknowledged_at,
            )
            for event in record.red_flags
        ],
        documents=[
            DocumentOut(
                document_id=document.document_id,
                kind=document.kind,
                status=document.status.value,
                page_count=document.page_count,
                confidence=document.confidence,
                low_confidence=document.low_confidence,
                rejection_reason=document.rejection_reason,
                uploaded_at=document.uploaded_at,
                processed_at=document.processed_at,
                url=(urls or {}).get(document.document_id),
            )
            for document in record.documents
        ],
        contradictions=[
            ContradictionOut(
                field_id=conflict.field_id,
                kind=conflict.kind.value,
                reported_today=(
                    conflict.reported_today.model_dump(mode="json")
                    if conflict.reported_today
                    else None
                ),
                from_record=conflict.from_record.model_dump(mode="json"),
                resolution=conflict.resolution,
            )
            for conflict in record.contradictions
        ],
        unresolved_fields=list(record.unanswered_fields()),
        needs_review=record.needs_review,
        provenance=record.provenance.model_dump(mode="json"),
        received_at=record.created_at,
        demo=demo,
    )


def report_out(bundle: ReportBundle, *, demo: bool = False) -> ReportOut:
    return ReportOut(
        intake_id=bundle.report.intake_id,
        language=bundle.report.language,
        template_version=bundle.report.template_version,
        report=bundle.report.model_dump(mode="json"),
        text=bundle.text,
        physician_verified_by=bundle.report.physician_verified_by,
        demo=demo,
    )


def worklist_out(worklist: Worklist, *, demo: bool = False) -> WorklistOut:
    def _entry(entry: object) -> WorklistEntryOut:
        return WorklistEntryOut.model_validate(entry, from_attributes=True)

    return WorklistOut(
        department_code=worklist.department_code,
        entries=[_entry(e) for e in worklist.entries],
        pending_alerts=[_entry(e) for e in worklist.pending_alerts],
        total=worklist.total,
        generated_at=worklist.generated_at,
        demo=demo,
    )
