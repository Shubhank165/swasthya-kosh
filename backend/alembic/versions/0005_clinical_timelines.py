"""The built history timeline, cached per intake and language.

Not a column on `reports`: `reports.body` is regenerated and overwritten on
every GET, so anything living there is derived rather than source. A timeline
built with a provider configured is the output of a model call that cost money
and must not be repeated every time a physician reloads the page — and two
readers opening the same report must see the same timeline, which they would not
if it were rebuilt per request.

`input_digest` is what makes the cache safe. It hashes the candidate set the
timeline was built from, so a new document or a newly linked prior visit
invalidates the row automatically and nothing has to remember to expire it.

Separate from `0004_patient_identifier_links` so either can be reverted alone.
The link table is useful without this; this is useless without the link table,
but reverting it does not take the history linking with it.

No backfill. A timeline for an intake taken before this migration is built on
the first read of its report, like every other one.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0005_clinical_timelines"
down_revision = "0004_patient_identifier_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinical_timelines",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("hospital_id", sa.String(length=64), nullable=False),
        sa.Column("intake_id", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model_id", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("omitted_count", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"]),
        sa.ForeignKeyConstraint(["intake_id"], ["intakes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "intake_id", "language", name="uq_clinical_timelines_intake_language"
        ),
    )
    op.create_index(
        op.f("ix_clinical_timelines_hospital_id"),
        "clinical_timelines",
        ["hospital_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_clinical_timelines_intake_id"),
        "clinical_timelines",
        ["intake_id"],
        unique=False,
    )
    op.create_index(
        "ix_clinical_timelines_hospital_intake",
        "clinical_timelines",
        ["hospital_id", "intake_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_clinical_timelines_hospital_intake", table_name="clinical_timelines"
    )
    op.drop_index(
        op.f("ix_clinical_timelines_intake_id"), table_name="clinical_timelines"
    )
    op.drop_index(
        op.f("ix_clinical_timelines_hospital_id"), table_name="clinical_timelines"
    )
    op.drop_table("clinical_timelines")
