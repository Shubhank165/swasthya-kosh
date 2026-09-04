"""add record_channel to clinical_facts

Revision ID: 7450cd467ddd
Revises: 6f50500eabf8
Create Date: 2026-09-01 01:34:43.494280
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '7450cd467ddd'
down_revision: str | None = '6f50500eabf8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Added with a server default so the column can be NOT NULL on a table that
    # already holds facts: every existing row is a live-channel fact. The default
    # is then dropped, because the application always supplies the value and a
    # lingering default would hide a future bug that forgot to.
    op.add_column(
        "clinical_facts",
        sa.Column(
            "record_channel",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    with op.batch_alter_table("clinical_facts") as batch:
        batch.alter_column("record_channel", server_default=None)


def downgrade() -> None:
    op.drop_column("clinical_facts", "record_channel")
