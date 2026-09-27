"""Rename `ayush_profiles` to `patient_profiles`.

The table was never Ayurveda-specific. Its columns are `field_id`, `status`,
`certainty`, `value` and `original_text` inside a JSON answer list, plus the
language and content version they were given against — a patient-level profile
that outlives a visit, which is exactly what `AyushProfileRecord`'s own
docstring argued for. Only the questionnaire it happened to carry was AYUSH.

So this renames the container and leaves the contents alone. No column changes,
no backfill, no data movement: the rows that were profiles are still profiles.
`0006` is left exactly as it shipped, because it has already run everywhere.

A rename rather than a drop-and-create for the obvious reason — the deployed
table holds real submissions, and recreating it would discard them.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision = "0007_rename_patient_profiles"
down_revision = "0006_ayush_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Old name -> new name. Indexes travel with the table on most backends, but
#: naming them explicitly keeps `op.f()`-generated names matching the models
#: after the rename instead of drifting apart silently.
_INDEXES: tuple[tuple[str, str], ...] = (
    ("ix_ayush_profiles_hospital_id", "ix_patient_profiles_hospital_id"),
    ("ix_ayush_profiles_patient_ref_value", "ix_patient_profiles_patient_ref_value"),
    ("ix_ayush_profiles_supersedes", "ix_patient_profiles_supersedes"),
    ("ix_ayush_profiles_patient", "ix_patient_profiles_patient"),
)


def _rename_indexes(pairs: Sequence[tuple[str, str]]) -> None:
    """Rename indexes where the backend has a statement for it.

    `ALTER INDEX` is PostgreSQL's, and PostgreSQL is what this deploys on.
    SQLite carries indexes across a table rename under their existing names and
    offers no way to rename them, so there is nothing to do and nothing broken
    by skipping it — the index still indexes the right column either way.
    """

    if op.get_bind().dialect.name != "postgresql":
        return
    for old, new in pairs:
        op.execute(f'ALTER INDEX IF EXISTS "{old}" RENAME TO "{new}"')


def upgrade() -> None:
    op.rename_table("ayush_profiles", "patient_profiles")
    _rename_indexes(_INDEXES)


def downgrade() -> None:
    _rename_indexes([(new, old) for old, new in _INDEXES])
    op.rename_table("patient_profiles", "ayush_profiles")
