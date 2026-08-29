"""initial schema

Revision ID: 20260828_0001
Revises: 
Create Date: 2026-08-28 11:50:28.057448
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260828_0001'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('application_users',
    sa.Column('issuer', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('username', sa.String(length=255), nullable=True),
    sa.Column('hms_username', sa.String(length=64), nullable=True),
    sa.Column('roles', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('clinic_id', sa.String(length=64), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('issuer', 'subject', name='uq_application_user_identity')
    )
    op.create_index(op.f('ix_application_users_clinic_id'), 'application_users', ['clinic_id'], unique=False)
    op.create_index(op.f('ix_application_users_subject'), 'application_users', ['subject'], unique=False)
    op.create_table('intake_sessions',
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('consent_status', sa.String(length=32), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_intake_sessions_status'), 'intake_sessions', ['status'], unique=False)
    op.create_table('triage_rules',
    sa.Column('hospital_id', sa.String(length=64), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('version', sa.String(length=32), nullable=False),
    sa.Column('priority', sa.String(length=16), nullable=False),
    sa.Column('condition', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('action', sa.Text(), nullable=False),
    sa.Column('explanation', sa.Text(), nullable=False),
    sa.Column('specialty_hint', sa.String(length=128), nullable=True),
    sa.Column('retired', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('hospital_id', 'code', name='uq_rule_per_hospital')
    )
    op.create_index(op.f('ix_triage_rules_code'), 'triage_rules', ['code'], unique=False)
    op.create_index(op.f('ix_triage_rules_hospital_id'), 'triage_rules', ['hospital_id'], unique=False)
    op.create_index(op.f('ix_triage_rules_priority'), 'triage_rules', ['priority'], unique=False)
    op.create_index(op.f('ix_triage_rules_retired'), 'triage_rules', ['retired'], unique=False)
    op.create_table('auth_sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('csrf_hash', sa.String(length=64), nullable=False),
    sa.Column('access_token_ciphertext', sa.Text(), nullable=False),
    sa.Column('refresh_token_ciphertext', sa.Text(), nullable=True),
    sa.Column('id_token_ciphertext', sa.Text(), nullable=True),
    sa.Column('access_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['application_users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_auth_sessions_expires_at'), 'auth_sessions', ['expires_at'], unique=False)
    op.create_index(op.f('ix_auth_sessions_revoked_at'), 'auth_sessions', ['revoked_at'], unique=False)
    op.create_index(op.f('ix_auth_sessions_token_hash'), 'auth_sessions', ['token_hash'], unique=True)
    op.create_index(op.f('ix_auth_sessions_user_id'), 'auth_sessions', ['user_id'], unique=False)
    op.create_table('intake_messages',
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('turn_index', sa.Integer(), nullable=False),
    sa.Column('asks_field', sa.String(length=64), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['intake_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_intake_messages_session_id'), 'intake_messages', ['session_id'], unique=False)
    op.create_table('patient_cases',
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('demographics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('hms_patient_id', sa.String(length=64), nullable=True),
    sa.Column('hospital_id', sa.String(length=64), nullable=False),
    sa.Column('specialty_hint', sa.String(length=128), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['intake_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_patient_cases_hms_patient_id'), 'patient_cases', ['hms_patient_id'], unique=False)
    op.create_index(op.f('ix_patient_cases_hospital_id'), 'patient_cases', ['hospital_id'], unique=False)
    op.create_index(op.f('ix_patient_cases_session_id'), 'patient_cases', ['session_id'], unique=True)
    op.create_table('allergy_medications',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('reaction_or_dose', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('source_turn', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['patient_cases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_allergy_medications_case_id'), 'allergy_medications', ['case_id'], unique=False)
    op.create_table('audit_events',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('actor', sa.String(length=128), nullable=False),
    sa.Column('action', sa.String(length=128), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['patient_cases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_events_action'), 'audit_events', ['action'], unique=False)
    op.create_index(op.f('ix_audit_events_case_id'), 'audit_events', ['case_id'], unique=False)
    op.create_table('care_tasks',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('task_type', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('priority', sa.String(length=16), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('hms_reference', sa.String(length=64), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['patient_cases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_care_tasks_case_id'), 'care_tasks', ['case_id'], unique=False)
    op.create_table('case_owners',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['patient_cases.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['application_users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_case_owners_case_id'), 'case_owners', ['case_id'], unique=True)
    op.create_index(op.f('ix_case_owners_user_id'), 'case_owners', ['user_id'], unique=False)
    op.create_table('clinical_reviews',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('decision', sa.String(length=16), nullable=False),
    sa.Column('reviewer_id', sa.String(length=64), nullable=False),
    sa.Column('reviewer_role', sa.String(length=64), nullable=False),
    sa.Column('edits', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['patient_cases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clinical_reviews_case_id'), 'clinical_reviews', ['case_id'], unique=False)
    op.create_table('clinical_summaries',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('sections', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('missing_information', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('generated_by', sa.String(length=32), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['patient_cases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clinical_summaries_case_id'), 'clinical_summaries', ['case_id'], unique=False)
    op.create_index(op.f('ix_clinical_summaries_kind'), 'clinical_summaries', ['kind'], unique=False)
    op.create_table('consultation_notes',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('doctor_id', sa.String(length=64), nullable=False),
    sa.Column('doctor_name', sa.String(length=128), nullable=True),
    sa.Column('consultation_mode', sa.String(length=16), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('prescription', sa.Text(), nullable=True),
    sa.Column('follow_up_instructions', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['patient_cases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_consultation_notes_case_id'), 'consultation_notes', ['case_id'], unique=False)
    op.create_table('medical_attachments',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=128), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('storage_uri', sa.Text(), nullable=False),
    sa.Column('extracted_text', sa.Text(), nullable=True),
    sa.Column('uploaded_by', sa.String(length=64), nullable=False),
    sa.Column('hms_reference', sa.String(length=128), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['patient_cases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_medical_attachments_case_id'), 'medical_attachments', ['case_id'], unique=False)
    op.create_table('patient_facts',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=64), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('source_turn', sa.Integer(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['patient_cases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_patient_facts_case_id'), 'patient_facts', ['case_id'], unique=False)
    op.create_index(op.f('ix_patient_facts_kind'), 'patient_facts', ['kind'], unique=False)
    op.create_table('routing_recommendations',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('department_id', sa.String(length=64), nullable=False),
    sa.Column('department_name', sa.String(length=128), nullable=False),
    sa.Column('doctor_id', sa.String(length=64), nullable=True),
    sa.Column('doctor_name', sa.String(length=128), nullable=True),
    sa.Column('appointment_type_id', sa.String(length=64), nullable=False),
    sa.Column('appointment_type_label', sa.String(length=128), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.Column('matched_keywords', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('suggested_slot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['patient_cases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_routing_recommendations_case_id'), 'routing_recommendations', ['case_id'], unique=False)
    op.create_table('triage_results',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('priority', sa.String(length=16), nullable=False),
    sa.Column('rule_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('rule_codes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['patient_cases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_triage_results_case_id'), 'triage_results', ['case_id'], unique=False)
    op.create_table('clinical_discrepancies',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('field_or_topic', sa.String(length=255), nullable=False),
    sa.Column('patient_stated', sa.Text(), nullable=False),
    sa.Column('document_says', sa.Text(), nullable=False),
    sa.Column('source_kind', sa.String(length=16), nullable=False),
    sa.Column('attachment_id', sa.Uuid(), nullable=True),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('requested_document_kind', sa.String(length=64), nullable=True),
    sa.Column('generated_by', sa.String(length=32), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['attachment_id'], ['medical_attachments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['case_id'], ['patient_cases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clinical_discrepancies_case_id'), 'clinical_discrepancies', ['case_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_clinical_discrepancies_case_id'), table_name='clinical_discrepancies')
    op.drop_table('clinical_discrepancies')
    op.drop_index(op.f('ix_triage_results_case_id'), table_name='triage_results')
    op.drop_table('triage_results')
    op.drop_index(op.f('ix_routing_recommendations_case_id'), table_name='routing_recommendations')
    op.drop_table('routing_recommendations')
    op.drop_index(op.f('ix_patient_facts_kind'), table_name='patient_facts')
    op.drop_index(op.f('ix_patient_facts_case_id'), table_name='patient_facts')
    op.drop_table('patient_facts')
    op.drop_index(op.f('ix_medical_attachments_case_id'), table_name='medical_attachments')
    op.drop_table('medical_attachments')
    op.drop_index(op.f('ix_consultation_notes_case_id'), table_name='consultation_notes')
    op.drop_table('consultation_notes')
    op.drop_index(op.f('ix_clinical_summaries_kind'), table_name='clinical_summaries')
    op.drop_index(op.f('ix_clinical_summaries_case_id'), table_name='clinical_summaries')
    op.drop_table('clinical_summaries')
    op.drop_index(op.f('ix_clinical_reviews_case_id'), table_name='clinical_reviews')
    op.drop_table('clinical_reviews')
    op.drop_index(op.f('ix_case_owners_user_id'), table_name='case_owners')
    op.drop_index(op.f('ix_case_owners_case_id'), table_name='case_owners')
    op.drop_table('case_owners')
    op.drop_index(op.f('ix_care_tasks_case_id'), table_name='care_tasks')
    op.drop_table('care_tasks')
    op.drop_index(op.f('ix_audit_events_case_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_action'), table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_index(op.f('ix_allergy_medications_case_id'), table_name='allergy_medications')
    op.drop_table('allergy_medications')
    op.drop_index(op.f('ix_patient_cases_session_id'), table_name='patient_cases')
    op.drop_index(op.f('ix_patient_cases_hospital_id'), table_name='patient_cases')
    op.drop_index(op.f('ix_patient_cases_hms_patient_id'), table_name='patient_cases')
    op.drop_table('patient_cases')
    op.drop_index(op.f('ix_intake_messages_session_id'), table_name='intake_messages')
    op.drop_table('intake_messages')
    op.drop_index(op.f('ix_auth_sessions_user_id'), table_name='auth_sessions')
    op.drop_index(op.f('ix_auth_sessions_token_hash'), table_name='auth_sessions')
    op.drop_index(op.f('ix_auth_sessions_revoked_at'), table_name='auth_sessions')
    op.drop_index(op.f('ix_auth_sessions_expires_at'), table_name='auth_sessions')
    op.drop_table('auth_sessions')
    op.drop_index(op.f('ix_triage_rules_retired'), table_name='triage_rules')
    op.drop_index(op.f('ix_triage_rules_priority'), table_name='triage_rules')
    op.drop_index(op.f('ix_triage_rules_hospital_id'), table_name='triage_rules')
    op.drop_index(op.f('ix_triage_rules_code'), table_name='triage_rules')
    op.drop_table('triage_rules')
    op.drop_index(op.f('ix_intake_sessions_status'), table_name='intake_sessions')
    op.drop_table('intake_sessions')
    op.drop_index(op.f('ix_application_users_subject'), table_name='application_users')
    op.drop_index(op.f('ix_application_users_clinic_id'), table_name='application_users')
    op.drop_table('application_users')
