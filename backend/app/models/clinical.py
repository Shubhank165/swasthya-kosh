"""Persistence.

**Every table carries `hospital_id`. Every query filters on it.** That is what
makes "a separate database per hospital" a later configuration change rather
than a rewrite — the alternative, discovering at deployment that tenancy was
assumed rather than enforced, is a data breach with a migration attached. The
filter is enforced at the session layer in `app/db/tenancy.py`, and
`tests/safety/test_tenancy.py` fails the build on a query that omits it.

`clinical_facts`, `red_flag_events`, `audit_log` and `ingest_raw` are
append-only. There is no UPDATE path and no DELETE path on any of them: a
correction inserts a new row whose `supersedes` points at the old one. The audit
trail is not a feature bolted onto the record — it *is* the record, and that is
only true if the table cannot be edited in place.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UtcDateTime

#: Every tenant-scoped table declares this exact column name. The tenancy guard
#: looks for it by name, so a table that spells it differently is a table the
#: guard cannot protect — and the guard fails closed on one it does not know.
TENANT_COLUMN = "hospital_id"


class HospitalRecord(Base, TimestampMixin):
    """A tenant.

    The one table without a `hospital_id` column, because it *is* the hospital.
    """

    __tablename__ = "hospitals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    #: Free text, e.g. "AIIA, New Delhi". Not an address record.
    location: Mapped[str | None] = mapped_column(String(256))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    departments: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    default_language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PatientRecord(Base, TimestampMixin):
    """Minimal patient identity, scoped to one hospital.

    Deliberately thin. MediKiosk is not a master patient index and it is not a
    record store: the hospital's HMIS owns demographics, and ABHA is an identity
    and consent-linking mechanism, not a history database.

    There is no `aadhaar` column, and there never will be. The last four digits
    travel on the intake as a matching aid and are not persisted as an
    identifier here.
    """

    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hospital_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    #: The hospital's own identifier — the UHID printed on the OPD card.
    external_mrn: Mapped[str | None] = mapped_column(String(128), index=True)
    #: ABHA address. Never required for basic intake.
    abha_address: Mapped[str | None] = mapped_column(String(128), index=True)
    display_name: Mapped[str | None] = mapped_column(String(256))
    birth_year: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String(32))
    preferred_language: Mapped[str | None] = mapped_column(String(16))

    __table_args__ = (
        # Scoped to the hospital, not global: two hospitals may legitimately use
        # the same UHID series.
        UniqueConstraint("hospital_id", "external_mrn", name="uq_patients_hospital_mrn"),
        Index("ix_patients_hospital_abha", "hospital_id", "abha_address"),
    )


class IntakeRecord(Base, TimestampMixin):
    """One intake received from a kiosk."""

    __tablename__ = "intakes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hospital_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    patient_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("patients.id"), index=True
    )
    #: `abha` | `hospital_id` | `aadhaar_last4` | `guest`
    patient_ref_type: Mapped[str] = mapped_column(String(32), nullable=False, default="guest")
    #: For `aadhaar_last4` this holds four digits and nothing more.
    patient_ref_value: Mapped[str | None] = mapped_column(String(128), index=True)
    #: `complete` | `partial` | `aborted_red_flag` | `abandoned`
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    reported_by: Mapped[str] = mapped_column(String(32), nullable=False, default="self")
    department_code: Mapped[str | None] = mapped_column(String(32), index=True)
    kiosk_id: Mapped[str | None] = mapped_column(String(64), index=True)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    engine_version: Mapped[str | None] = mapped_column(String(64))
    content_version: Mapped[str | None] = mapped_column(String(64))
    record_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    #: True when the payload failed its contract and the repair model
    #: restructured it. Drives `repair_rate`, which is a real quality metric.
    repaired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: True when even repair failed. The raw payload is in `ingest_raw`.
    needs_manual_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    #: Set when a physician opens the report. Drives the worklist `seen` state.
    seen_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    seen_by: Mapped[str | None] = mapped_column(String(64))

    facts: Mapped[list[ClinicalFactRecord]] = relationship(
        back_populates="intake", cascade="all, delete-orphan", order_by="ClinicalFactRecord.seq"
    )

    __table_args__ = (
        Index("ix_intakes_hospital_received", "hospital_id", "received_at"),
        Index("ix_intakes_hospital_department", "hospital_id", "department_code"),
    )


class ClinicalFactRecord(Base):
    """One fact revision. Append-only.

    Every provenance field is a real column rather than a JSON blob, because
    these are the fields the report queries and the fields an auditor will ask
    about. `value` and `source_ref` are JSON because they are typed unions whose
    shape is versioned with the canonical record.
    """

    __tablename__ = "clinical_facts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hospital_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    #: Insertion order within an intake. The append-only log's sequence.
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    intake_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("intakes.id"), nullable=False, index=True
    )
    field_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    section: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    #: `answered` | `unresolved` | `not_asked` | `not_applicable` | `refused`.
    #: Five values, stored as five values. Nothing collapses them to a boolean.
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    certainty: Mapped[str] = mapped_column(String(32), nullable=False)
    #: `{"kind": "duration", "magnitude": 3, "unit": "day"}`. NULL for every
    #: status but `answered`.
    value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    #: The patient's own words, preserved beside the normalised value.
    original_text: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    reported_by: Mapped[str] = mapped_column(String(32), nullable=False)
    physician_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    repaired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    needs_verification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recorded_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    supersedes: Mapped[str | None] = mapped_column(String(64), index=True)
    note: Mapped[str | None] = mapped_column(Text)

    intake: Mapped[IntakeRecord] = relationship(back_populates="facts")

    __table_args__ = (
        UniqueConstraint("intake_id", "seq", name="uq_clinical_facts_intake_id_seq"),
        Index("ix_clinical_facts_intake_field", "intake_id", "field_id"),
        Index("ix_clinical_facts_hospital_field", "hospital_id", "field_id"),
    )


class DocumentRecordRow(Base, TimestampMixin):
    """An uploaded prescription, report or discharge summary."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hospital_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    intake_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("intakes.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    #: `received` | `processing` | `processed` | `rejected_quality` | `failed`
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="received")
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Object-storage key. Never a URL — URLs are signed on demand and expire.
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    overall_confidence: Mapped[float | None] = mapped_column(Float)
    #: Surfaced on the report rather than hidden: the physician is told when the
    #: machine was unsure.
    low_confidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(256))
    #: Which identifier kinds the redaction pass masked, and how many of each.
    #: Counts only — never the values.
    redactions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="mock")
    model_id: Mapped[str | None] = mapped_column(String(128))
    demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    document_date: Mapped[date | None] = mapped_column(Date)
    issuing_facility: Mapped[str | None] = mapped_column(String(256))
    #: Per-page redacted text, for the evidence panel. Post-redaction only.
    page_text: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    uploaded_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    items: Mapped[list[DocumentItemRecord]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentItemRecord(Base):
    """One extracted line from a document, with its bounding box."""

    __tablename__ = "document_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hospital_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.id"), nullable=False, index=True
    )
    intake_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    #: `medicine` | `diagnosis` | `lab_result` | `procedure` | `other`
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    #: Post-redaction. The pre-redaction text exists only in the image.
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: `{"x":..,"y":..,"width":..,"height":..}`, normalised 0..1.
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    needs_verification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    label: Mapped[str | None] = mapped_column(String(256))
    #: The typed payload — a `Medicine` or a `LabResult`.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    #: `in_range` | `below_range` | `above_range` | `range_unavailable` |
    #: `not_comparable`. Always computed against the range printed on this
    #: document, never a hardcoded one.
    range_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="range_unavailable"
    )

    document: Mapped[DocumentRecordRow] = relationship(back_populates="items")


class RedFlagEventRecord(Base):
    """A criterion the Jetson fired, and the human decision on it.

    The backend runs no rules. It receives events, surfaces them, and records who
    acknowledged them. `acknowledged_by` is what authorises anything downstream:
    nothing in this system may act on an alert whose acknowledgement is null.
    """

    __tablename__ = "red_flag_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hospital_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    intake_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("intakes.id"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(256))
    fired_at_turn: Mapped[int | None] = mapped_column(Integer)
    criteria_met: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    #: Which engine fired it. A rule id means nothing without the version of the
    #: rule set that defined it.
    engine_version: Mapped[str | None] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    acknowledgement_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("intake_id", "rule_id", name="uq_red_flag_events_intake_rule"),
    )


class ReportRecord(Base, TimestampMixin):
    """A generated physician report and its verification state."""

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hospital_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    intake_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("intakes.id"), nullable=False, index=True
    )
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    template_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    #: The structured report. The rendered text is derived from it on read, not
    #: stored twice — two copies of a clinical document diverge.
    body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    physician_verified_by: Mapped[str | None] = mapped_column(String(64), index=True)
    physician_verified_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    service_date: Mapped[date | None] = mapped_column(Date, index=True)

    __table_args__ = (
        UniqueConstraint("intake_id", "language", name="uq_reports_intake_language"),
    )


class ConsentArtefact(Base):
    """Immutable record of what a patient agreed to.

    The DPDP Act 2023 requires we can produce this: the exact text shown, the
    language it was shown in, the audio actually played, the purposes granted,
    when, and by whom. A boolean would not survive a single question from a
    regulator. Immutable by policy — a withdrawal writes a new artefact.
    """

    __tablename__ = "consent_artefacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hospital_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    intake_id: Mapped[str | None] = mapped_column(String(64), index=True)
    patient_id: Mapped[str | None] = mapped_column(String(64), index=True)
    consent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Hash of the exact notice text shown, so the wording can be proven later.
    notice_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    notice_text: Mapped[str] = mapped_column(Text, nullable=False)
    #: Asset id of the audio actually played, when the notice was read aloud.
    audio_asset_id: Mapped[str | None] = mapped_column(String(128))
    granted_purposes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    refused_purposes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    granting_party: Mapped[str] = mapped_column(String(32), nullable=False)
    granting_party_name: Mapped[str | None] = mapped_column(String(256))
    granted_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    supersedes: Mapped[str | None] = mapped_column(String(64))


class IngestRawRecord(Base):
    """A payload that could not be normalised, kept whole.

    **Never discard input.** A malformed payload is seven minutes of a patient's
    answers; the parser being unhappy with it is our problem, not theirs. The
    row holds the original body so a human — or a normalizer that ships next
    week — can recover the intake.

    This is the one table that legitimately holds unstructured clinical text.
    It is not indexed on content, never joined into a read path, and the API
    exposes it to `admin` only.
    """

    __tablename__ = "ingest_raw"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hospital_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    #: The intake id claimed by the payload, when it had a readable one.
    claimed_intake_id: Mapped[str | None] = mapped_column(String(128), index=True)
    schema_version: Mapped[str | None] = mapped_column(String(16))
    #: `contract_invalid` | `repair_failed` | `unsupported_version`
    reason: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    #: The validation errors, structurally. Never the payload's clinical text.
    error_detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    repair_attempted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    resolved_by: Mapped[str | None] = mapped_column(String(64))


class AuditLogEntry(Base):
    """Append-only audit of every clinical record change.

    Actor, before, after, reason. `before`/`after` hold structural summaries —
    field ids, statuses, flags — not raw clinical text, so the audit log does not
    become a second, less careful PHI store.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64))


class IdempotencyKeyRecord(Base):
    """A completed mutating request, keyed by its `Idempotency-Key`.

    A kiosk on a hospital LAN loses the network mid-submission more often than
    anyone would like. When it retries, the retry must return the original
    response and create nothing.
    """

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(256), primary_key=True)
    hospital_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)


class TerminologyConcept(Base):
    """A code from NAMASTE, ICD-11 TM2 or ICD-11 MMS.

    Reference data, shared across hospitals — the one table besides `hospitals`
    with no tenant column, because a code system does not belong to a hospital.
    """

    __tablename__ = "terminology_concepts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    system: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    display: Mapped[str] = mapped_column(String(256), nullable=False)
    definition: Mapped[str | None] = mapped_column(Text)
    discipline: Mapped[str | None] = mapped_column(String(32))
    synonyms: Mapped[list[str]] = mapped_column(JSON, default=list)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="seed")

    __table_args__ = (
        UniqueConstraint("system", "code", name="uq_terminology_concepts_system_code"),
    )


class TerminologyMapping(Base):
    """A ConceptMap row. Absent where no mapping exists — never guessed."""

    __tablename__ = "terminology_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_system: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_code: Mapped[str] = mapped_column(String(64), nullable=False)
    #: FHIR ConceptMap vocabulary: equivalent | wider | narrower | relatedto | inexact
    equivalence: Mapped[str] = mapped_column(String(32), nullable=False, default="relatedto")
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "source_code",
            "target_system",
            "target_code",
            name="uq_terminology_mappings_source_target",
        ),
    )


#: Tables that are reference data or the tenant list itself, and so are exempt
#: from the tenant filter. Everything not named here must carry `hospital_id`
#: and must be queried with it — `tests/safety/test_tenancy.py` enumerates the
#: metadata and fails on any table that slipped through.
TENANT_EXEMPT_TABLES: frozenset[str] = frozenset(
    {"hospitals", "terminology_concepts", "terminology_mappings", "alembic_version"}
)
