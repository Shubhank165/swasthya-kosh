"""Clinical persistence.

`clinical_facts` is append-only. There is no UPDATE path and no DELETE path: a
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
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class PatientRecord(Base, TimestampMixin):
    """Minimal patient identity.

    Deliberately thin. MediKiosk is not a master patient index and it is not a
    record store: the hospital HMIS owns demographics, and ABHA is an identity
    and consent-linking mechanism, not a history database.
    """

    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: Hospital's own identifier — the UHID printed on the OPD card.
    external_mrn: Mapped[str | None] = mapped_column(String(128), index=True)
    #: ABHA address. Never required for basic intake.
    abha_address: Mapped[str | None] = mapped_column(String(128), index=True)
    display_name: Mapped[str | None] = mapped_column(String(256))
    birth_year: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String(32))
    preferred_language: Mapped[str | None] = mapped_column(String(16))

    __table_args__ = (
        UniqueConstraint("external_mrn", name="uq_patients_external_mrn"),
    )


class IntakeRecord(Base, TimestampMixin):
    """One history-taking session."""

    __tablename__ = "intakes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("patients.id"), index=True
    )
    #: MediKiosk-owned lifecycle. Never derived from a ticket's queue state.
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    #: Monotonic. Guards against a reconnecting kiosk clobbering newer answers.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    language: Mapped[str | None] = mapped_column(String(16))
    reporter_role: Mapped[str] = mapped_column(String(32), nullable=False, default="self")
    active_pathway: Mapped[str | None] = mapped_column(String(64))
    active_ros_groups: Mapped[list[str]] = mapped_column(JSON, default=list)
    ayurveda_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    declined_concepts: Mapped[list[str]] = mapped_column(JSON, default=list)
    consent_artefact_id: Mapped[str | None] = mapped_column(String(64), index=True)
    kiosk_id: Mapped[str | None] = mapped_column(String(64), index=True)
    department_code: Mapped[str | None] = mapped_column(String(32), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    facts: Mapped[list[ClinicalFactRecord]] = relationship(
        back_populates="intake", cascade="all, delete-orphan", order_by="ClinicalFactRecord.seq"
    )


class ClinicalFactRecord(Base):
    """One fact revision. Append-only.

    Every provenance field from the domain `ClinicalFact` is a real column rather
    than a JSON blob, because these are the fields the physician report queries
    and the fields an auditor will ask about.
    """

    __tablename__ = "clinical_facts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: Insertion order within an intake. The append-only log's sequence.
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    intake_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("intakes.id"), nullable=False, index=True
    )
    concept_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    concept_system: Mapped[str | None] = mapped_column(String(64))
    concept_code: Mapped[str | None] = mapped_column(String(64))
    concept_display: Mapped[str | None] = mapped_column(String(256))
    section: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    certainty: Mapped[str] = mapped_column(String(32), nullable=False)
    temporality: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Typed value, serialised as {"kind": ..., ...}. None for ABSENT/UNKNOWN.
    value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    #: The patient's own words, preserved beside the normalised concept.
    original_expression: Mapped[str | None] = mapped_column(Text)
    original_language: Mapped[str | None] = mapped_column(String(16))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reported_by: Mapped[str] = mapped_column(String(32), nullable=False)
    patient_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    physician_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes: Mapped[str | None] = mapped_column(String(64), index=True)
    note: Mapped[str | None] = mapped_column(Text)

    intake: Mapped[IntakeRecord] = relationship(back_populates="facts")

    __table_args__ = (
        UniqueConstraint("intake_id", "seq", name="uq_clinical_facts_intake_id_seq"),
        Index("ix_clinical_facts_intake_concept", "intake_id", "concept_id"),
    )


class ConsentArtefact(Base):
    """Immutable record of what a patient agreed to.

    DPDP Act 2023 requires we can produce this: the exact text version, the
    language it was presented in, the audio actually played, the purposes
    granted, when, and by whom. Immutable by policy — a withdrawal writes a new
    artefact, it does not edit this one.
    """

    __tablename__ = "consent_artefacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
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
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set on the superseding artefact when consent is re-taken or withdrawn.
    supersedes: Mapped[str | None] = mapped_column(String(64))


class DocumentRecordRow(Base, TimestampMixin):
    """An uploaded prescription, report or discharge summary."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    intake_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("intakes.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Surfaced on the report rather than hidden: the physician is told to check
    #: the original when the machine was unsure.
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    overall_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RedFlagAlertRecord(Base):
    """A fired red-flag rule, and the human decision on it.

    `acknowledged_by` is what authorises an escalation. Nothing in the system may
    escalate a ticket citing an alert whose acknowledgement column is null.
    """

    __tablename__ = "red_flag_alerts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    intake_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("intakes.id"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    clinical_source: Mapped[str] = mapped_column(String(256), nullable=False)
    criteria_description: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_fact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    notify: Mapped[str] = mapped_column(String(32), nullable=False, default="triage")
    #: A hint for the human, never applied automatically.
    priority_hint: Mapped[str | None] = mapped_column(String(32))
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_by: Mapped[str | None] = mapped_column(String(64))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissal_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("intake_id", "rule_id", name="uq_red_flag_alerts_intake_id_rule_id"),
    )


class AuditLogEntry(Base):
    """Append-only audit of every clinical record change.

    Actor, before, after, reason. `before`/`after` hold structural summaries, not
    raw clinical text, so the audit log itself is not a second PHI store.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
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
    """A completed mutating request, keyed by its Idempotency-Key."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(256), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TerminologyConcept(Base):
    """A code from NAMASTE, ICD-11 TM2 or ICD-11 MMS."""

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


class ReportRecord(Base, TimestampMixin):
    """A generated physician report and its verification state."""

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    intake_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("intakes.id"), nullable=False, index=True
    )
    intake_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    coverage_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: Structured summary. The rendered text is derived from it, not stored twice.
    body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    physician_verified_by: Mapped[str | None] = mapped_column(String(64), index=True)
    physician_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    service_date: Mapped[date | None] = mapped_column(Date, index=True)
