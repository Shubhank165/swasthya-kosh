"""Intake request and response DTOs.

Two things these types refuse to do, deliberately. They never expose a boolean
where the domain has a five-value status, and they never omit provenance from a
fact: a client that receives a fact receives everything needed to challenge it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.domain.clinical.enums import (
    AnswerShape,
    Certainty,
    FactStatus,
    IntakeState,
    ReporterRole,
    Section,
    Severity,
    SourceType,
    Temporality,
)
from app.schemas.common import ApiModel


class CreateIntakeRequest(ApiModel):
    kiosk_id: str | None = None
    department_code: str | None = None
    patient_id: str | None = None
    language: str | None = None


class UpdateIntakeRequest(ApiModel):
    language: str | None = None
    reporter: ReporterRole | None = None
    ayurveda_enabled: bool | None = None
    patient_id: str | None = None


class SubmitAnswerRequest(ApiModel):
    concept: str
    #: `null` means no answer was given. It is recorded as UNKNOWN, never as "no".
    value: Any | None = None
    original_expression: str | None = None
    original_language: str | None = None
    source_type: SourceType = SourceType.TOUCH
    reported_by: ReporterRole | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    #: The patient chose not to answer. Distinct from "does not know".
    declined: bool = False
    segment_id: str | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    actor: str | None = None
    #: Optimistic-concurrency guard for a reconnecting kiosk.
    expected_revision: int | None = None


class AnswerSpecOut(ApiModel):
    type: AnswerShape
    options: list[str] = Field(default_factory=list)
    unit: str | None = None
    minimum: float | None = Field(default=None, alias="min")
    maximum: float | None = Field(default=None, alias="max")


class StepOut(ApiModel):
    """One question. `selection_reason` is exposed on purpose: the machine's
    reasoning is auditable by anyone holding the API response."""

    kind: Literal["step"] = "step"
    concept: str
    question: str
    language: str
    answer: AnswerSpecOut
    section: Section
    required: bool
    skippable: bool
    origin: str
    source_pathway: str
    selection_reason: str
    touch_options: list[str] = Field(default_factory=list)
    confirming_value: str | None = None
    prompts: dict[str, str] = Field(default_factory=dict)


class CompleteOut(ApiModel):
    kind: Literal["complete"] = "complete"
    reason: str
    required_total: int
    required_settled: int
    optional_asked: int


class SourceRefOut(ApiModel):
    kind: str
    segment_id: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    document_id: str | None = None
    page: int | None = None
    bbox: dict[str, float] | None = None
    entered_by: str | None = None


class FactOut(ApiModel):
    """A fact with its full provenance. Nothing is elided."""

    fact_id: str
    concept: str
    display: str | None = None
    section: Section
    status: FactStatus
    certainty: Certainty
    temporality: Temporality
    value: str | None = None
    original_expression: str | None = None
    original_language: str | None = None
    source_type: SourceType
    source_ref: SourceRefOut
    confidence: float
    reported_by: ReporterRole
    patient_confirmed: bool
    physician_verified: bool
    recorded_at: str
    supersedes: str | None = None


class MissingFieldOut(ApiModel):
    concept: str
    section: Section
    required: bool
    reason: str
    description: str


class SectionCoverageOut(ApiModel):
    section: Section
    required: int
    captured: int
    not_applicable: int
    unanswered: int
    declined: int
    percentage: float
    is_complete: bool
    missing: list[MissingFieldOut] = Field(default_factory=list)


class CoverageOut(ApiModel):
    """Coverage as both a number and the actual list of gaps.

    The percentage alone is useless to a doctor; "allergy history not asked" is
    what they act on.
    """

    percentage: float
    is_complete: bool
    required_total: int
    required_captured: int
    required_not_applicable: int
    required_declined: int
    optional_captured: int
    optional_total: int
    sections: list[SectionCoverageOut] = Field(default_factory=list)
    missing_required: list[MissingFieldOut] = Field(default_factory=list)


class AlertOut(ApiModel):
    """A red-flag alert.

    `patient_safe_label` is the only field permitted on a patient-facing surface;
    it never names a condition.
    """

    alert_id: str | None = None
    rule_id: str
    severity: Severity
    label: str
    patient_safe_label: str
    clinical_source: str
    criteria_description: str
    supporting_facts: list[str] = Field(default_factory=list)
    notify: str
    priority_hint: str | None = None
    raised_at: str | None = None
    acknowledged_by: str | None = None
    acknowledged_at: str | None = None
    dismissed_by: str | None = None
    dismissal_reason: str | None = None
    is_open: bool = True


class ConflictSideOut(ApiModel):
    fact_id: str
    statement: str
    source_type: SourceType
    source_label: str
    confidence: float
    recorded_at_label: str
    patient_confirmed: bool


class ContradictionOut(ApiModel):
    """Both sides of a disagreement, never resolved by the system."""

    concept: str
    kind: str
    reported_today: ConflictSideOut | None = None
    from_record: ConflictSideOut
    resolution: str
    rendered: str


class IntakeOut(ApiModel):
    intake_id: str
    state: IntakeState
    revision: int
    language: str | None = None
    reporter: ReporterRole
    active_pathway: str | None = None
    ayurveda_enabled: bool
    patient_id: str | None = None
    consent_artefact_id: str | None = None
    declined: list[str] = Field(default_factory=list)
    facts: list[FactOut] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)


class IntakeSnapshotOut(ApiModel):
    intake: IntakeOut
    next_step: StepOut | CompleteOut
    coverage: CoverageOut
    alerts: list[AlertOut] = Field(default_factory=list)
    newly_raised: list[AlertOut] = Field(default_factory=list)
    contradictions: list[ContradictionOut] = Field(default_factory=list)


class ConfirmRequest(ApiModel):
    """Patient confirmation. `corrections` names concepts they say are wrong."""

    corrections: list[str] = Field(default_factory=list)


class PhysicianVerifyRequest(ApiModel):
    physician_id: str
    #: Verify only these concepts. Omit to verify everything outstanding.
    concepts: list[str] | None = None


class SummaryLineOut(ApiModel):
    text: str
    fact_ids: list[str] = Field(default_factory=list)
    original_expression: str | None = None
    original_language: str | None = None


class SummarySectionOut(ApiModel):
    section: Section
    title: str
    lines: list[SummaryLineOut] = Field(default_factory=list)


class ReportOut(ApiModel):
    intake_id: str
    coverage_percentage: float
    sections: list[SummarySectionOut] = Field(default_factory=list)
    unresolved: list[SummaryLineOut] = Field(default_factory=list)
    conflicts: list[ContradictionOut] = Field(default_factory=list)
    alerts: list[AlertOut] = Field(default_factory=list)
    physician_verified: bool
    #: The plain-text report, exactly as a physician reads it.
    rendered_text: str


class EvidenceOut(ApiModel):
    fact_id: str
    concept: str
    status: FactStatus
    certainty: Certainty
    value: str | None = None
    original_expression: str | None = None
    original_language: str | None = None
    source_type: SourceType
    source_ref: SourceRefOut
    confidence: float
    reported_by: ReporterRole
    patient_confirmed: bool
    physician_verified: bool
    recorded_at: str
    revisions: list[dict[str, Any]] = Field(default_factory=list)


class ConsentRequest(ApiModel):
    intake_id: str
    language: str
    granted_purposes: list[str]
    refused_purposes: list[str] = Field(default_factory=list)
    granting_party: ReporterRole = ReporterRole.SELF
    granting_party_name: str | None = None
    audio_asset_id: str | None = None


class ConsentOut(ApiModel):
    consent_id: str
    intake_id: str | None = None
    consent_version: str
    language: str
    notice_hash: str
    granted_purposes: list[str]
    refused_purposes: list[str]
    granting_party: str
    granted_at: str
    withdrawn_at: str | None = None


class AcknowledgeAlertRequest(ApiModel):
    user_id: str


class DismissAlertRequest(ApiModel):
    user_id: str
    reason: str
