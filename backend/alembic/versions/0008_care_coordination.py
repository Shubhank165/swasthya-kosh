"""Orders, slots and stock: what happens after the consultation.

Three tables for the four acts that used to leave the building as paper — a
lab test, a scan, a referral, a prescription — plus the two things they need
to be more than an instruction: a slot with room in it, and a shelf with the
medicine on it.

Deliberately small. `service_slots` is declared capacity, not a booking engine;
`pharmacy_stock` is a count and an expiry date, not inventory management. The
hospital's own systems remain the system of record for both, and a second one
that disagrees with them would be worse than none.

All three are tenant-scoped, so `tests/safety/test_tenancy.py` covers them
without being told to. No backfill: nothing existed before this.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.models.base import UtcDateTime

revision = "0008_care_coordination"
down_revision = "0007_rename_patient_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "care_orders",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("hospital_id", sa.String(length=64), nullable=False),
        sa.Column("intake_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("display", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("destination", sa.String(length=64), nullable=True),
        sa.Column("slot_id", sa.String(length=64), nullable=True),
        sa.Column("slot_at", UtcDateTime(), nullable=True),
        sa.Column("ordered_by", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("updated_at", UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["intake_id"], ["intakes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("hospital_id", "intake_id", "kind", "status", "destination", "slot_id", "ordered_by"):
        op.create_index(op.f(f"ix_care_orders_{column}"), "care_orders", [column], unique=False)

    op.create_table(
        "service_slots",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("hospital_id", sa.String(length=64), nullable=False),
        sa.Column("destination", sa.String(length=64), nullable=False),
        sa.Column("starts_at", UtcDateTime(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("booked", sa.Integer(), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("updated_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("hospital_id", "destination", "starts_at"):
        op.create_index(op.f(f"ix_service_slots_{column}"), "service_slots", [column], unique=False)

    op.create_table(
        "pharmacy_stock",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("hospital_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("display", sa.String(length=256), nullable=False),
        sa.Column("on_hand", sa.Integer(), nullable=False),
        sa.Column("reorder_level", sa.Integer(), nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("updated_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hospital_id", "code", name="uq_pharmacy_stock_hospital_code"),
    )
    for column in ("hospital_id", "code"):
        op.create_index(op.f(f"ix_pharmacy_stock_{column}"), "pharmacy_stock", [column], unique=False)


def downgrade() -> None:
    for column in ("hospital_id", "code"):
        op.drop_index(op.f(f"ix_pharmacy_stock_{column}"), table_name="pharmacy_stock")
    op.drop_table("pharmacy_stock")
    for column in ("hospital_id", "destination", "starts_at"):
        op.drop_index(op.f(f"ix_service_slots_{column}"), table_name="service_slots")
    op.drop_table("service_slots")
    for column in ("hospital_id", "intake_id", "kind", "status", "destination", "slot_id", "ordered_by"):
        op.drop_index(op.f(f"ix_care_orders_{column}"), table_name="care_orders")
    op.drop_table("care_orders")
