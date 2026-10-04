"""The id of a red-flag event could not hold the ids it is built from.

`RedFlagEventRecord.id` is `rf_{intake_id}_{rule_id}` — a deterministic
surrogate, so that replaying an ingest updates one row rather than inserting a
second. Its column was `String(64)`, and `intake_id` is itself `String(64)`
while `rule_id` is `String(128)`. The composite therefore could not fit in its
own column for any rule id longer than 24 characters, and the insert failed with
`value too long for type character varying(64)` — a 500 on ingest, after the
device had already stopped asking questions.

Two of the five **critical** criteria in `clinical/questioning/redflags.yaml`
are over that budget:

    breathing_difficulty_at_rest        28
    headache_sudden_with_vision_change  34

so the two criteria most likely to need a physician immediately were the two
that could not be recorded. A device firing either got a 500, retried, got
another 500, and eventually dropped the submission.

256 is `3 + 64 + 1 + 128` rounded up, so the id now fits whatever the columns it
is composed from permit. Uniqueness never depended on the length: it is enforced
by `uq_red_flag_events_intake_rule`.

Widening is safe in both directions here — no existing value can be longer than
64, so the downgrade cannot truncate anything that is already stored.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0009_widen_red_flag_event_id"
down_revision = "0008_care_coordination"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _retype(*, frm: int, to: int) -> None:
    """Change the width of `red_flag_events.id`, where that means anything.

    `ALTER COLUMN ... TYPE` is PostgreSQL's, and PostgreSQL is what this
    deploys on. SQLite — which the migration tests run against — does not
    enforce `VARCHAR(n)` at all: it stores whatever it is given regardless of
    the declared length. So on SQLite the bug this migration fixes cannot
    happen and the fix has nothing to do, which is why skipping is correct
    rather than merely convenient.
    """

    if op.get_bind().dialect.name != "postgresql":
        return
    op.alter_column(
        "red_flag_events",
        "id",
        existing_type=sa.String(length=frm),
        type_=sa.String(length=to),
        existing_nullable=False,
    )


def upgrade() -> None:
    _retype(frm=64, to=256)


def downgrade() -> None:
    _retype(frm=256, to=64)
