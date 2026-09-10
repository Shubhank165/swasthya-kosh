"""API request and response models.

Every response that could be mistaken for live data carries the flags that say
what it is: `demo` when the deployment is serving fixtures, `source` when an
identity answer came from a mock. Those fields are not diagnostics — they are
what stops a screenshot from claiming something the system did not do.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.record import DocumentKind, FactValue, PhysicianAction


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ErrorResponse(ApiModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(ApiModel):
    """What the kiosk gets back from `POST /intakes/ingest`."""

    intake_id: str
    status: str
    #: Fields the device asked but could not settle. The useful half of the
    #: response: staff can fill these before the consultation.
    unresolved_fields: list[str] = Field(default_factory=list)
    needs_review: bool = False
    repaired: bool = False
    needs_manual_review: bool = False
    red_flags: list[str] = Field(default_factory=list)
    contradictions: int = 0
    demo: bool = False


class FactOut(ApiModel):
    fact_id: str
    field_id: str
    label: str
    status: str
    value: dict[str, Any] | None = None
    rendered: str | None = None
    original_text: str | None = None
    language: str | None = None
    certainty: str
    channel: str
    section: str
    confidence: float | None = None
    physician_verified: bool = False
    #: `verified` | `amended` | `rejected`, and absent on everything the
    #: pipeline wrote. The dashboard renders an amended line differently from a
    #: merely confirmed one — a value a doctor typed is a different claim.
    physician_action: str | None = None
    repaired: bool = False
    needs_verification: bool = False
    #: Present when this answer came from a previous visit — §B1. The dashboard
    #: renders it as carried forward, with the date and whether the patient
    #: confirmed it today; `confirmed_today: null` means it was not re-asked,
    #: which is not the same as the patient declining.
    carried_forward: dict[str, Any] | None = None
    source: dict[str, Any]
    recorded_at: datetime


class RedFlagOut(ApiModel):
    rule_id: str
    severity: str
    label: str | None = None
    fired_at_turn: int | None = None
    criteria_met: list[str] = Field(default_factory=list)
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None


class DocumentOut(ApiModel):
    document_id: str
    kind: DocumentKind
    status: str
    page_count: int = 1
    confidence: float | None = None
    low_confidence: bool = False
    rejection_reason: str | None = None
    uploaded_at: datetime | None = None
    processed_at: datetime | None = None
    #: Short-lived and never public. Absent for a document read on the device,
    #: where no image was ever uploaded.
    url: str | None = None


class PatientDocumentOut(ApiModel):
    """One document, as its own patient may see it.

    **Deliberately narrower than `DocumentOut`.** No confidence figure and no
    extracted content of any kind: §8 keeps unverified extraction away from the
    patient, because a value read off a prescription and shown back to them
    without a physician between is a diagnosis surface.

    What is left is the photograph, when it was added, whether the hospital has
    processed it, and — where it was refused — why, which is the one piece of
    feedback a patient can actually act on by taking the picture again.

    `kind` stays. It is a document type, not a finding: telling somebody the
    page they photographed was filed as a prescription asserts nothing about
    their health.
    """

    document_id: str
    kind: DocumentKind
    status: str
    page_count: int = 1
    rejection_reason: str | None = None
    uploaded_at: datetime | None = None
    processed_at: datetime | None = None
    #: Short-lived and never public.
    url: str | None = None


class ContradictionOut(ApiModel):
    field_id: str
    kind: str
    reported_today: dict[str, Any] | None = None
    from_record: dict[str, Any]
    resolution: str


class IntakeOut(ApiModel):
    intake_id: str
    hospital_id: str
    status: str
    language: str
    department_code: str | None = None
    patient_ref: dict[str, Any]
    facts: list[FactOut] = Field(default_factory=list)
    red_flags: list[RedFlagOut] = Field(default_factory=list)
    documents: list[DocumentOut] = Field(default_factory=list)
    contradictions: list[ContradictionOut] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)
    needs_review: bool = False
    provenance: dict[str, Any] = Field(default_factory=dict)
    received_at: datetime | None = None
    seen_at: datetime | None = None
    demo: bool = False


class ReportOut(ApiModel):
    """The report, structured and rendered.

    Both, always. The structure is what the dashboard links from; the text is
    what a physician reads, prints, or pastes into the HMIS when the integration
    is not there yet.
    """

    intake_id: str
    language: str
    template_version: str
    report: dict[str, Any]
    text: str
    physician_verified_by: str | None = None
    demo: bool = False


class DocumentUploadResponse(ApiModel):
    document_id: str
    status: str
    url: str | None = None
    demo: bool = False


class KioskIdentityOut(ApiModel):
    """The principal behind a kiosk bearer token — the payload of
    `GET /kiosk/whoami`. No patient data; a provisioning check only."""

    role: str
    hospital_id: str
    user_id: str


class DocumentResultsRequest(ApiModel):
    """An extraction the Jetson produced on-device.

    The image stays on the device; only the structured result crosses the
    network. A hospital that will not let prescriptions leave the building gets
    the same report as one that will.
    """

    extraction: dict[str, Any]
    kind: DocumentKind = DocumentKind.OTHER


class ResolveRequest(ApiModel):
    type: str = "guest"
    value: str | None = None


class ABHALinkRequest(ApiModel):
    #: An ABHA address, `name@sbx`. Never required: §7.2 makes linking optional
    #: and the app works with a phone number alone.
    #:
    #: Constrained here rather than checked in the route, because an empty value
    #: reaches `PatientRef` — which requires one for a non-guest reference — and
    #: raises there as a 500. A malformed address is the caller's mistake and
    #: deserves a 422; it is not an ABHA outage and must not be confused with
    #: one, which answers `verified: false` and lets the intake continue.
    abha_address: str = Field(min_length=1, max_length=128)


class ResolveResponse(ApiModel):
    ref: dict[str, Any]
    patient_id: str | None = None
    verified: bool = False
    known_here: bool = False
    #: `"mock"` when the answer came from the mock ABHA provider. Passed
    #: through so a dashboard can say so, out loud, on screen.
    source: str | None = None
    notice: str | None = None


class HistoryResponse(ApiModel):
    ref: dict[str, Any]
    hospital_id: str
    intakes: list[dict[str, Any]] = Field(default_factory=list)
    carry_forward: list[dict[str, Any]] = Field(default_factory=list)
    scope_note: str


class WorklistEntryOut(ApiModel):
    intake_id: str
    department_code: str | None = None
    state: str
    intake_status: str
    arrived_at: datetime
    language: str
    unacknowledged_alerts: int = 0
    unresolved_count: int = 0
    contradiction_count: int = 0
    needs_verification: bool = False
    repaired: bool = False
    #: Repair could not rescue the payload. A person looks before the patient is
    #: seen — §4.1 asks the dashboard to surface these prominently, and it
    #: cannot without being told which they are.
    needs_manual_review: bool = False
    patient_ref_type: str = "guest"
    seen_at: datetime | None = None


class WorklistOut(ApiModel):
    department_code: str | None = None
    entries: list[WorklistEntryOut] = Field(default_factory=list)
    pending_alerts: list[WorklistEntryOut] = Field(default_factory=list)
    total: int = 0
    generated_at: datetime | None = None
    demo: bool = False


class AcknowledgeRequest(ApiModel):
    rule_id: str
    note: str | None = None


class AcknowledgeResponse(ApiModel):
    intake_id: str
    rule_id: str
    acknowledged_by: str
    acknowledged_at: datetime


class VerifyRequest(ApiModel):
    """A physician confirming the record, or the fields they name.

    Omitting `field_ids` verifies everything settled. Unsettled fields are
    skipped whatever is passed: there is nothing to confirm about a question
    that was never answered.
    """

    field_ids: list[str] | None = None
    language: str | None = None


class FactVerifyRequest(ApiModel):
    """A physician acting on one fact — 3/3 §6.

    Three actions, and the wording matters. `verified` says the record is right;
    `amended` supplies a corrected value; `rejected` says the field was never
    established. **Rejection is not a `no`** — see
    `Fact.rejected_by_physician` — and there is deliberately no fourth action
    that would let one be written as the other.
    """

    action: PhysicianAction
    #: Required for `amended`, refused for the other two. The typed value, not a
    #: string: the dashboard renders what the record model can hold, so a
    #: correction that cannot be expressed as a `FactValue` is a correction the
    #: report could not have printed in the first place.
    value: FactValue | None = None
    reason: str | None = Field(default=None, max_length=500)


class AlertOut(ApiModel):
    """One fired red-flag criterion — §4.3.

    `label` is the rule's own fixed wording — "urgent clinical review criterion
    triggered" — and **never a condition name**. `criteria_met` names the
    answers that met the rule, which is what lets a clinician judge it; the rule
    does not get to name a diagnosis it did not make.
    """

    alert_id: str
    intake_id: str
    department_code: str | None = None
    rule_id: str
    severity: str
    label: str | None = None
    criteria_met: list[str] = Field(default_factory=list)
    fired_at_turn: int | None = None
    engine_version: str | None = None
    received_at: datetime
    arrived_at: datetime
    intake_status: str
    language: str = "en"
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    acknowledgement_note: str | None = None


class AlertListOut(ApiModel):
    alerts: list[AlertOut] = Field(default_factory=list)
    unacknowledged: int = 0
    generated_at: datetime | None = None
    demo: bool = False


class CorrectionRateOut(ApiModel):
    """How often a physician had to correct the pipeline — §6, §B3.

    The denominator is facts a physician reviewed, not every fact stored. A
    field nobody looked at says nothing about extraction quality, and including
    it would let the rate be improved by ingesting more intakes.

    `correction_rate` is `null`, not `0.0`, when nothing has been reviewed yet —
    a zero on an empty denominator reads as "never wrong", which is a claim this
    has not earned.
    """

    facts_reviewed: int = 0
    verified: int = 0
    amended: int = 0
    rejected: int = 0
    correction_rate: float | None = None
    intakes_reviewed: int = 0
    demo: bool = False


class ConsentRequest(ApiModel):
    intake_id: str | None = None
    patient_id: str | None = None
    consent_version: str
    language: str
    notice_text: str
    granted_purposes: list[str] = Field(default_factory=list)
    refused_purposes: list[str] = Field(default_factory=list)
    granting_party: str = "self"
    granting_party_name: str | None = None
    audio_asset_id: str | None = None


class ConsentOut(ApiModel):
    consent_id: str
    intake_id: str | None = None
    consent_version: str
    language: str
    notice_hash: str
    granted_purposes: list[str] = Field(default_factory=list)
    refused_purposes: list[str] = Field(default_factory=list)
    granting_party: str
    granted_at: datetime
    withdrawn_at: datetime | None = None


class MetricsOut(ApiModel):
    """Operational counters worth stating out loud.

    `repair_rate` is the one to watch: it should fall as the Jetson's extractor
    improves.
    """

    intakes: int = 0
    repaired: int = 0
    needs_manual_review: int = 0
    repair_rate: float = 0.0


# --- patient app (2/3 §7, §12) -----------------------------------------------


class OTPRequestBody(ApiModel):
    phone: str


class OTPRequestResponse(ApiModel):
    challenge_id: str
    expires_at: str
    #: Present only when the mock sender is in use *and* the environment is not
    #: production. It is how a demo on a laptop with no signal completes a
    #: sign-in; `PatientAuthService` refuses to populate it otherwise, so this
    #: field cannot become a live-code leak by configuration alone.
    code: str | None = None
    delivery: str


class OTPVerifyBody(ApiModel):
    challenge_id: str
    code: str


class PatientSessionResponse(ApiModel):
    token: str
    expires_at: str
    #: The opaque reference this patient's records are keyed by. Returned so the
    #: app can tell two accounts apart in its own storage; it is a peppered HMAC
    #: and reverses to nothing.
    patient_ref: str


class DepartmentOut(ApiModel):
    code: str
    display: str


class HospitalOut(ApiModel):
    hospital_id: str
    display_name: str
    location: str | None = None
    timezone: str
    default_language: str
    departments: list[DepartmentOut] = Field(default_factory=list)


class HospitalListResponse(ApiModel):
    hospitals: list[HospitalOut] = Field(default_factory=list)
