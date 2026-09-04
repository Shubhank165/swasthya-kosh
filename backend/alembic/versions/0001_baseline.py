"""Baseline schema.

The first migration of the ingest-oriented backend. It replaces the interview
schema entirely — that one is in `stale/alembic_versions/`, kept because the
code it belonged to is kept, and not chained to because the tables it created no
longer exist in any form worth migrating.

`alembic upgrade head` from an empty database gives a working stack. There is no
downgrade path to the old schema and there should not be one: a downgrade that
silently dropped every intake would be worse than no downgrade at all.

Revision ID: 0001_baseline
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.models.base

revision: str = '0001_baseline'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('audit_log',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('hospital_id', sa.String(length=64), nullable=False),
    sa.Column('occurred_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.Column('actor_id', sa.String(length=64), nullable=False),
    sa.Column('actor_role', sa.String(length=32), nullable=False),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=False),
    sa.Column('entity_id', sa.String(length=64), nullable=False),
    sa.Column('before', sa.JSON(), nullable=True),
    sa.Column('after', sa.JSON(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_log'))
    )
    op.create_index(op.f('ix_audit_log_action'), 'audit_log', ['action'], unique=False)
    op.create_index(op.f('ix_audit_log_actor_id'), 'audit_log', ['actor_id'], unique=False)
    op.create_index(op.f('ix_audit_log_entity_id'), 'audit_log', ['entity_id'], unique=False)
    op.create_index(op.f('ix_audit_log_hospital_id'), 'audit_log', ['hospital_id'], unique=False)
    op.create_index(op.f('ix_audit_log_occurred_at'), 'audit_log', ['occurred_at'], unique=False)
    op.create_table('consent_artefacts',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('hospital_id', sa.String(length=64), nullable=False),
    sa.Column('intake_id', sa.String(length=64), nullable=True),
    sa.Column('patient_id', sa.String(length=64), nullable=True),
    sa.Column('consent_version', sa.String(length=32), nullable=False),
    sa.Column('language', sa.String(length=16), nullable=False),
    sa.Column('notice_hash', sa.String(length=64), nullable=False),
    sa.Column('notice_text', sa.Text(), nullable=False),
    sa.Column('audio_asset_id', sa.String(length=128), nullable=True),
    sa.Column('granted_purposes', sa.JSON(), nullable=False),
    sa.Column('refused_purposes', sa.JSON(), nullable=False),
    sa.Column('granting_party', sa.String(length=32), nullable=False),
    sa.Column('granting_party_name', sa.String(length=256), nullable=True),
    sa.Column('granted_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.Column('withdrawn_at', app.models.base.UtcDateTime(timezone=True), nullable=True),
    sa.Column('supersedes', sa.String(length=64), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_consent_artefacts'))
    )
    op.create_index(op.f('ix_consent_artefacts_hospital_id'), 'consent_artefacts', ['hospital_id'], unique=False)
    op.create_index(op.f('ix_consent_artefacts_intake_id'), 'consent_artefacts', ['intake_id'], unique=False)
    op.create_index(op.f('ix_consent_artefacts_patient_id'), 'consent_artefacts', ['patient_id'], unique=False)
    op.create_table('hospitals',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('display_name', sa.String(length=256), nullable=False),
    sa.Column('location', sa.String(length=256), nullable=True),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('departments', sa.JSON(), nullable=False),
    sa.Column('default_language', sa.String(length=16), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.Column('updated_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_hospitals'))
    )
    op.create_table('idempotency_keys',
    sa.Column('key', sa.String(length=128), nullable=False),
    sa.Column('endpoint', sa.String(length=256), nullable=False),
    sa.Column('hospital_id', sa.String(length=64), nullable=False),
    sa.Column('request_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('response_body', sa.JSON(), nullable=False),
    sa.Column('status_code', sa.Integer(), nullable=False),
    sa.Column('created_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key', 'endpoint', name=op.f('pk_idempotency_keys'))
    )
    op.create_index(op.f('ix_idempotency_keys_hospital_id'), 'idempotency_keys', ['hospital_id'], unique=False)
    op.create_table('ingest_raw',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('hospital_id', sa.String(length=64), nullable=False),
    sa.Column('claimed_intake_id', sa.String(length=128), nullable=True),
    sa.Column('schema_version', sa.String(length=16), nullable=True),
    sa.Column('reason', sa.String(length=64), nullable=False),
    sa.Column('error_detail', sa.JSON(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('payload_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('repair_attempted', sa.Boolean(), nullable=False),
    sa.Column('received_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.Column('resolved_at', app.models.base.UtcDateTime(timezone=True), nullable=True),
    sa.Column('resolved_by', sa.String(length=64), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ingest_raw'))
    )
    op.create_index(op.f('ix_ingest_raw_claimed_intake_id'), 'ingest_raw', ['claimed_intake_id'], unique=False)
    op.create_index(op.f('ix_ingest_raw_hospital_id'), 'ingest_raw', ['hospital_id'], unique=False)
    op.create_index(op.f('ix_ingest_raw_payload_fingerprint'), 'ingest_raw', ['payload_fingerprint'], unique=False)
    op.create_index(op.f('ix_ingest_raw_reason'), 'ingest_raw', ['reason'], unique=False)
    op.create_index(op.f('ix_ingest_raw_received_at'), 'ingest_raw', ['received_at'], unique=False)
    op.create_table('terminology_concepts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('system', sa.String(length=32), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('display', sa.String(length=256), nullable=False),
    sa.Column('definition', sa.Text(), nullable=True),
    sa.Column('discipline', sa.String(length=32), nullable=True),
    sa.Column('synonyms', sa.JSON(), nullable=False),
    sa.Column('version', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_terminology_concepts')),
    sa.UniqueConstraint('system', 'code', name='uq_terminology_concepts_system_code')
    )
    op.create_index(op.f('ix_terminology_concepts_system'), 'terminology_concepts', ['system'], unique=False)
    op.create_table('terminology_mappings',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('source_system', sa.String(length=32), nullable=False),
    sa.Column('source_code', sa.String(length=64), nullable=False),
    sa.Column('target_system', sa.String(length=32), nullable=False),
    sa.Column('target_code', sa.String(length=64), nullable=False),
    sa.Column('equivalence', sa.String(length=32), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_terminology_mappings')),
    sa.UniqueConstraint('source_system', 'source_code', 'target_system', 'target_code', name='uq_terminology_mappings_source_target')
    )
    op.create_index(op.f('ix_terminology_mappings_source_code'), 'terminology_mappings', ['source_code'], unique=False)
    op.create_index(op.f('ix_terminology_mappings_source_system'), 'terminology_mappings', ['source_system'], unique=False)
    op.create_index(op.f('ix_terminology_mappings_target_system'), 'terminology_mappings', ['target_system'], unique=False)
    op.create_table('patients',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('hospital_id', sa.String(length=64), nullable=False),
    sa.Column('external_mrn', sa.String(length=128), nullable=True),
    sa.Column('abha_address', sa.String(length=128), nullable=True),
    sa.Column('display_name', sa.String(length=256), nullable=True),
    sa.Column('birth_year', sa.Integer(), nullable=True),
    sa.Column('sex', sa.String(length=32), nullable=True),
    sa.Column('preferred_language', sa.String(length=16), nullable=True),
    sa.Column('created_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.Column('updated_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['hospital_id'], ['hospitals.id'], name=op.f('fk_patients_hospital_id_hospitals')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_patients')),
    sa.UniqueConstraint('hospital_id', 'external_mrn', name='uq_patients_hospital_mrn')
    )
    op.create_index(op.f('ix_patients_abha_address'), 'patients', ['abha_address'], unique=False)
    op.create_index(op.f('ix_patients_external_mrn'), 'patients', ['external_mrn'], unique=False)
    op.create_index('ix_patients_hospital_abha', 'patients', ['hospital_id', 'abha_address'], unique=False)
    op.create_index(op.f('ix_patients_hospital_id'), 'patients', ['hospital_id'], unique=False)
    op.create_table('intakes',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('hospital_id', sa.String(length=64), nullable=False),
    sa.Column('patient_id', sa.String(length=64), nullable=True),
    sa.Column('patient_ref_type', sa.String(length=32), nullable=False),
    sa.Column('patient_ref_value', sa.String(length=128), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('language', sa.String(length=16), nullable=False),
    sa.Column('reported_by', sa.String(length=32), nullable=False),
    sa.Column('department_code', sa.String(length=32), nullable=True),
    sa.Column('kiosk_id', sa.String(length=64), nullable=True),
    sa.Column('schema_version', sa.String(length=16), nullable=False),
    sa.Column('engine_version', sa.String(length=64), nullable=True),
    sa.Column('content_version', sa.String(length=64), nullable=True),
    sa.Column('record_version', sa.String(length=16), nullable=False),
    sa.Column('repaired', sa.Boolean(), nullable=False),
    sa.Column('needs_manual_review', sa.Boolean(), nullable=False),
    sa.Column('started_at', app.models.base.UtcDateTime(timezone=True), nullable=True),
    sa.Column('completed_at', app.models.base.UtcDateTime(timezone=True), nullable=True),
    sa.Column('received_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.Column('seen_at', app.models.base.UtcDateTime(timezone=True), nullable=True),
    sa.Column('seen_by', sa.String(length=64), nullable=True),
    sa.Column('created_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.Column('updated_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['hospital_id'], ['hospitals.id'], name=op.f('fk_intakes_hospital_id_hospitals')),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_intakes_patient_id_patients')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_intakes'))
    )
    op.create_index(op.f('ix_intakes_department_code'), 'intakes', ['department_code'], unique=False)
    op.create_index('ix_intakes_hospital_department', 'intakes', ['hospital_id', 'department_code'], unique=False)
    op.create_index(op.f('ix_intakes_hospital_id'), 'intakes', ['hospital_id'], unique=False)
    op.create_index('ix_intakes_hospital_received', 'intakes', ['hospital_id', 'received_at'], unique=False)
    op.create_index(op.f('ix_intakes_kiosk_id'), 'intakes', ['kiosk_id'], unique=False)
    op.create_index(op.f('ix_intakes_patient_id'), 'intakes', ['patient_id'], unique=False)
    op.create_index(op.f('ix_intakes_patient_ref_value'), 'intakes', ['patient_ref_value'], unique=False)
    op.create_index(op.f('ix_intakes_received_at'), 'intakes', ['received_at'], unique=False)
    op.create_index(op.f('ix_intakes_status'), 'intakes', ['status'], unique=False)
    op.create_table('clinical_facts',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('hospital_id', sa.String(length=64), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('intake_id', sa.String(length=64), nullable=False),
    sa.Column('field_id', sa.String(length=128), nullable=False),
    sa.Column('section', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('certainty', sa.String(length=32), nullable=False),
    sa.Column('value', sa.JSON(), nullable=True),
    sa.Column('original_text', sa.Text(), nullable=True),
    sa.Column('language', sa.String(length=16), nullable=True),
    sa.Column('channel', sa.String(length=32), nullable=False),
    sa.Column('source_ref', sa.JSON(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('reported_by', sa.String(length=32), nullable=False),
    sa.Column('physician_verified', sa.Boolean(), nullable=False),
    sa.Column('repaired', sa.Boolean(), nullable=False),
    sa.Column('needs_verification', sa.Boolean(), nullable=False),
    sa.Column('recorded_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.Column('supersedes', sa.String(length=64), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['intake_id'], ['intakes.id'], name=op.f('fk_clinical_facts_intake_id_intakes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clinical_facts')),
    sa.UniqueConstraint('intake_id', 'seq', name='uq_clinical_facts_intake_id_seq')
    )
    op.create_index(op.f('ix_clinical_facts_channel'), 'clinical_facts', ['channel'], unique=False)
    op.create_index(op.f('ix_clinical_facts_field_id'), 'clinical_facts', ['field_id'], unique=False)
    op.create_index('ix_clinical_facts_hospital_field', 'clinical_facts', ['hospital_id', 'field_id'], unique=False)
    op.create_index(op.f('ix_clinical_facts_hospital_id'), 'clinical_facts', ['hospital_id'], unique=False)
    op.create_index('ix_clinical_facts_intake_field', 'clinical_facts', ['intake_id', 'field_id'], unique=False)
    op.create_index(op.f('ix_clinical_facts_intake_id'), 'clinical_facts', ['intake_id'], unique=False)
    op.create_index(op.f('ix_clinical_facts_section'), 'clinical_facts', ['section'], unique=False)
    op.create_index(op.f('ix_clinical_facts_supersedes'), 'clinical_facts', ['supersedes'], unique=False)
    op.create_table('documents',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('hospital_id', sa.String(length=64), nullable=False),
    sa.Column('intake_id', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('content_type', sa.String(length=64), nullable=False),
    sa.Column('storage_key', sa.String(length=512), nullable=False),
    sa.Column('byte_size', sa.Integer(), nullable=False),
    sa.Column('page_count', sa.Integer(), nullable=False),
    sa.Column('overall_confidence', sa.Float(), nullable=True),
    sa.Column('low_confidence', sa.Boolean(), nullable=False),
    sa.Column('rejection_reason', sa.String(length=256), nullable=True),
    sa.Column('redactions', sa.JSON(), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('model_id', sa.String(length=128), nullable=True),
    sa.Column('demo', sa.Boolean(), nullable=False),
    sa.Column('document_date', sa.Date(), nullable=True),
    sa.Column('issuing_facility', sa.String(length=256), nullable=True),
    sa.Column('page_text', sa.JSON(), nullable=False),
    sa.Column('uploaded_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.Column('processed_at', app.models.base.UtcDateTime(timezone=True), nullable=True),
    sa.Column('created_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.Column('updated_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['intake_id'], ['intakes.id'], name=op.f('fk_documents_intake_id_intakes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_documents'))
    )
    op.create_index(op.f('ix_documents_hospital_id'), 'documents', ['hospital_id'], unique=False)
    op.create_index(op.f('ix_documents_intake_id'), 'documents', ['intake_id'], unique=False)
    op.create_table('red_flag_events',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('hospital_id', sa.String(length=64), nullable=False),
    sa.Column('intake_id', sa.String(length=64), nullable=False),
    sa.Column('rule_id', sa.String(length=128), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('label', sa.String(length=256), nullable=True),
    sa.Column('fired_at_turn', sa.Integer(), nullable=True),
    sa.Column('criteria_met', sa.JSON(), nullable=False),
    sa.Column('engine_version', sa.String(length=64), nullable=True),
    sa.Column('received_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.Column('acknowledged_by', sa.String(length=64), nullable=True),
    sa.Column('acknowledged_at', app.models.base.UtcDateTime(timezone=True), nullable=True),
    sa.Column('acknowledgement_note', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['intake_id'], ['intakes.id'], name=op.f('fk_red_flag_events_intake_id_intakes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_red_flag_events')),
    sa.UniqueConstraint('intake_id', 'rule_id', name='uq_red_flag_events_intake_rule')
    )
    op.create_index(op.f('ix_red_flag_events_acknowledged_by'), 'red_flag_events', ['acknowledged_by'], unique=False)
    op.create_index(op.f('ix_red_flag_events_hospital_id'), 'red_flag_events', ['hospital_id'], unique=False)
    op.create_index(op.f('ix_red_flag_events_intake_id'), 'red_flag_events', ['intake_id'], unique=False)
    op.create_index(op.f('ix_red_flag_events_rule_id'), 'red_flag_events', ['rule_id'], unique=False)
    op.create_index(op.f('ix_red_flag_events_severity'), 'red_flag_events', ['severity'], unique=False)
    op.create_table('reports',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('hospital_id', sa.String(length=64), nullable=False),
    sa.Column('intake_id', sa.String(length=64), nullable=False),
    sa.Column('language', sa.String(length=16), nullable=False),
    sa.Column('template_version', sa.String(length=16), nullable=False),
    sa.Column('body', sa.JSON(), nullable=False),
    sa.Column('generated_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.Column('physician_verified_by', sa.String(length=64), nullable=True),
    sa.Column('physician_verified_at', app.models.base.UtcDateTime(timezone=True), nullable=True),
    sa.Column('service_date', sa.Date(), nullable=True),
    sa.Column('created_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.Column('updated_at', app.models.base.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['intake_id'], ['intakes.id'], name=op.f('fk_reports_intake_id_intakes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reports')),
    sa.UniqueConstraint('intake_id', 'language', name='uq_reports_intake_language')
    )
    op.create_index(op.f('ix_reports_hospital_id'), 'reports', ['hospital_id'], unique=False)
    op.create_index(op.f('ix_reports_intake_id'), 'reports', ['intake_id'], unique=False)
    op.create_index(op.f('ix_reports_physician_verified_by'), 'reports', ['physician_verified_by'], unique=False)
    op.create_index(op.f('ix_reports_service_date'), 'reports', ['service_date'], unique=False)
    op.create_table('document_items',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('hospital_id', sa.String(length=64), nullable=False),
    sa.Column('document_id', sa.String(length=64), nullable=False),
    sa.Column('intake_id', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('raw_text', sa.Text(), nullable=False),
    sa.Column('page', sa.Integer(), nullable=False),
    sa.Column('bbox', sa.JSON(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('needs_verification', sa.Boolean(), nullable=False),
    sa.Column('label', sa.String(length=256), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=True),
    sa.Column('range_status', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_document_items_document_id_documents')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_items'))
    )
    op.create_index(op.f('ix_document_items_document_id'), 'document_items', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_items_hospital_id'), 'document_items', ['hospital_id'], unique=False)
    op.create_index(op.f('ix_document_items_intake_id'), 'document_items', ['intake_id'], unique=False)
    op.create_index(op.f('ix_document_items_kind'), 'document_items', ['kind'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_document_items_kind'), table_name='document_items')
    op.drop_index(op.f('ix_document_items_intake_id'), table_name='document_items')
    op.drop_index(op.f('ix_document_items_hospital_id'), table_name='document_items')
    op.drop_index(op.f('ix_document_items_document_id'), table_name='document_items')
    op.drop_table('document_items')
    op.drop_index(op.f('ix_reports_service_date'), table_name='reports')
    op.drop_index(op.f('ix_reports_physician_verified_by'), table_name='reports')
    op.drop_index(op.f('ix_reports_intake_id'), table_name='reports')
    op.drop_index(op.f('ix_reports_hospital_id'), table_name='reports')
    op.drop_table('reports')
    op.drop_index(op.f('ix_red_flag_events_severity'), table_name='red_flag_events')
    op.drop_index(op.f('ix_red_flag_events_rule_id'), table_name='red_flag_events')
    op.drop_index(op.f('ix_red_flag_events_intake_id'), table_name='red_flag_events')
    op.drop_index(op.f('ix_red_flag_events_hospital_id'), table_name='red_flag_events')
    op.drop_index(op.f('ix_red_flag_events_acknowledged_by'), table_name='red_flag_events')
    op.drop_table('red_flag_events')
    op.drop_index(op.f('ix_documents_intake_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_hospital_id'), table_name='documents')
    op.drop_table('documents')
    op.drop_index(op.f('ix_clinical_facts_supersedes'), table_name='clinical_facts')
    op.drop_index(op.f('ix_clinical_facts_section'), table_name='clinical_facts')
    op.drop_index(op.f('ix_clinical_facts_intake_id'), table_name='clinical_facts')
    op.drop_index('ix_clinical_facts_intake_field', table_name='clinical_facts')
    op.drop_index(op.f('ix_clinical_facts_hospital_id'), table_name='clinical_facts')
    op.drop_index('ix_clinical_facts_hospital_field', table_name='clinical_facts')
    op.drop_index(op.f('ix_clinical_facts_field_id'), table_name='clinical_facts')
    op.drop_index(op.f('ix_clinical_facts_channel'), table_name='clinical_facts')
    op.drop_table('clinical_facts')
    op.drop_index(op.f('ix_intakes_status'), table_name='intakes')
    op.drop_index(op.f('ix_intakes_received_at'), table_name='intakes')
    op.drop_index(op.f('ix_intakes_patient_ref_value'), table_name='intakes')
    op.drop_index(op.f('ix_intakes_patient_id'), table_name='intakes')
    op.drop_index(op.f('ix_intakes_kiosk_id'), table_name='intakes')
    op.drop_index('ix_intakes_hospital_received', table_name='intakes')
    op.drop_index(op.f('ix_intakes_hospital_id'), table_name='intakes')
    op.drop_index('ix_intakes_hospital_department', table_name='intakes')
    op.drop_index(op.f('ix_intakes_department_code'), table_name='intakes')
    op.drop_table('intakes')
    op.drop_index(op.f('ix_patients_hospital_id'), table_name='patients')
    op.drop_index('ix_patients_hospital_abha', table_name='patients')
    op.drop_index(op.f('ix_patients_external_mrn'), table_name='patients')
    op.drop_index(op.f('ix_patients_abha_address'), table_name='patients')
    op.drop_table('patients')
    op.drop_index(op.f('ix_terminology_mappings_target_system'), table_name='terminology_mappings')
    op.drop_index(op.f('ix_terminology_mappings_source_system'), table_name='terminology_mappings')
    op.drop_index(op.f('ix_terminology_mappings_source_code'), table_name='terminology_mappings')
    op.drop_table('terminology_mappings')
    op.drop_index(op.f('ix_terminology_concepts_system'), table_name='terminology_concepts')
    op.drop_table('terminology_concepts')
    op.drop_index(op.f('ix_ingest_raw_received_at'), table_name='ingest_raw')
    op.drop_index(op.f('ix_ingest_raw_reason'), table_name='ingest_raw')
    op.drop_index(op.f('ix_ingest_raw_payload_fingerprint'), table_name='ingest_raw')
    op.drop_index(op.f('ix_ingest_raw_hospital_id'), table_name='ingest_raw')
    op.drop_index(op.f('ix_ingest_raw_claimed_intake_id'), table_name='ingest_raw')
    op.drop_table('ingest_raw')
    op.drop_index(op.f('ix_idempotency_keys_hospital_id'), table_name='idempotency_keys')
    op.drop_table('idempotency_keys')
    op.drop_table('hospitals')
    op.drop_index(op.f('ix_consent_artefacts_patient_id'), table_name='consent_artefacts')
    op.drop_index(op.f('ix_consent_artefacts_intake_id'), table_name='consent_artefacts')
    op.drop_index(op.f('ix_consent_artefacts_hospital_id'), table_name='consent_artefacts')
    op.drop_table('consent_artefacts')
    op.drop_index(op.f('ix_audit_log_occurred_at'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_hospital_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_entity_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_actor_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_action'), table_name='audit_log')
    op.drop_table('audit_log')
