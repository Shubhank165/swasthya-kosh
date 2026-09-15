"""The AYUSH/Prakriti self-report, filed against a patient rather than a visit.

Its own table, and not a row in `clinical_facts`, because `clinical_facts`
requires an `intake_id`: every fact there is something a patient said on a
particular day. A Prakriti profile is answered once, describes the person, and
outlives any one OPD attendance. The alternative considered and rejected was a
synthetic intake to hang it from — which would surface as a phantom visit in
the worklist, the metrics and the purge path, and fail somewhere nobody was
looking months later.

Carries `hospital_id` like every other tenant-scoped table. A constitution
arguably belongs to the person rather than the clinic, but `TENANT_EXEMPT_TABLES`
is a short list with a written justification per entry, and exempting this one
would mean sharing patient data across tenants on a clinical argument — not a
trade a migration gets to make quietly.

`answers` is one JSON document rather than a row per field. `clinical_facts`
needs a row each because an interview appends them one at a time; a profile
arrives complete and is read complete, the way `clinical_timelines.events`
already stores a collection. A correction is a new row pointing at the old one
through `supersedes` — there is no UPDATE path, per decision 4.

No backfill. There is nothing to backfill: before this migration the answers
never left the patient's device.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0006_ayush_profiles"
down_revision = "0005_clinical_timelines"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ayush_profiles",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("hospital_id", sa.String(length=64), nullable=False),
        sa.Column("patient_ref_type", sa.String(length=32), nullable=False),
        sa.Column("patient_ref_value", sa.String(length=128), nullable=False),
        sa.Column("content_version", sa.String(length=64), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ayush_profiles_hospital_id"),
        "ayush_profiles",
        ["hospital_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ayush_profiles_patient_ref_value"),
        "ayush_profiles",
        ["patient_ref_value"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ayush_profiles_supersedes"),
        "ayush_profiles",
        ["supersedes"],
        unique=False,
    )
    op.create_index(
        "ix_ayush_profiles_patient",
        "ayush_profiles",
        ["hospital_id", "patient_ref_type", "patient_ref_value"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ayush_profiles_patient", table_name="ayush_profiles")
    op.drop_index(op.f("ix_ayush_profiles_supersedes"), table_name="ayush_profiles")
    op.drop_index(
        op.f("ix_ayush_profiles_patient_ref_value"), table_name="ayush_profiles"
    )
    op.drop_index(op.f("ix_ayush_profiles_hospital_id"), table_name="ayush_profiles")
    op.drop_table("ayush_profiles")
