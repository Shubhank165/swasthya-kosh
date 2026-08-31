"""ORM base and shared column types."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, TypeDecorator
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class UtcDateTime(TypeDecorator[datetime]):
    """A timestamp that is always timezone-aware UTC in Python.

    Postgres `timestamptz` round-trips awareness; SQLite does not, and returns a
    naive value. A naive datetime in a medical record is a bug waiting for a
    shift change — and it raises the moment it meets an aware one — so awareness
    is restored here, at the one boundary where it can be lost.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

#: Explicit naming so Alembic autogenerate produces stable, reviewable migrations
#: instead of names that churn between runs.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {dict[str, Any]: __import__("sqlalchemy").JSON}


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    """Created/updated stamps. Timezone-aware always."""

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
