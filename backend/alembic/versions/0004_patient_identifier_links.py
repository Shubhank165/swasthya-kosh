"""Every identifier that has ever resolved to one patient, as a table.

A patient's prior visits are found by the exact `(patient_ref_type,
patient_ref_value)` an intake was filed under — never by `patients.id`, which
is written NULL at intake creation. So somebody who signed in by phone in the
app and later linked an ABHA address had two histories that could not see each
other, and setting `patients.abha_address` would not have joined them: that
column says which ABHA is on the chart, not which references point at this
person.

Rows pointing at the same `patient_id` are the same person. The unique
constraint is what makes an identifier resolve to exactly one of them.

For a phone reference the value is the peppered HMAC the app already sends —
the same shape `patient_sessions.phone_ref` holds — and never a phone number.

No backfill. Existing intakes stay reachable by the reference they were filed
under, which is what they were reachable by before; this table only adds
aliases, and an alias nobody asserted is not one to invent.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0004_patient_identifier_links"
down_revision = "0003_physician_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patient_identifier_links",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("hospital_id", sa.String(length=64), nullable=False),
        sa.Column("patient_id", sa.String(length=64), nullable=True),
        sa.Column("ref_type", sa.String(length=32), nullable=False),
        sa.Column("ref_value", sa.String(length=256), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "hospital_id",
            "ref_type",
            "ref_value",
            name="uq_patient_links_hospital_ref",
        ),
    )
    op.create_index(
        op.f("ix_patient_identifier_links_hospital_id"),
        "patient_identifier_links",
        ["hospital_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_patient_identifier_links_patient_id"),
        "patient_identifier_links",
        ["patient_id"],
        unique=False,
    )
    op.create_index(
        "ix_patient_links_hospital_patient",
        "patient_identifier_links",
        ["hospital_id", "patient_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_patient_links_hospital_patient", table_name="patient_identifier_links"
    )
    op.drop_index(
        op.f("ix_patient_identifier_links_patient_id"),
        table_name="patient_identifier_links",
    )
    op.drop_index(
        op.f("ix_patient_identifier_links_hospital_id"),
        table_name="patient_identifier_links",
    )
    op.drop_table("patient_identifier_links")
