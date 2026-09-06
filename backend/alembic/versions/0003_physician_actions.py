"""What a physician did to a fact, as a column.

The correction rate — the proportion of facts a doctor amends — is the metric
this project reports in place of the shelved evaluation harness's figures. It
has to come from a column rather than a `LIKE` over the free-text note, or the
number changes the first time somebody rewords the note. See
`app.domain.record.PhysicianAction` and 3/3 section 6.

Nullable with no backfill: every fact written before this migration was written
by the pipeline, and NULL is exactly what that means.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0003_physician_actions"
down_revision = "0002_patient_app_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clinical_facts",
        sa.Column("physician_action", sa.String(length=16), nullable=True),
    )
    op.create_index(
        op.f("ix_clinical_facts_physician_action"),
        "clinical_facts",
        ["physician_action"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_clinical_facts_physician_action"), table_name="clinical_facts"
    )
    op.drop_column("clinical_facts", "physician_action")
