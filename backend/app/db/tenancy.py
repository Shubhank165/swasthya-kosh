"""Tenant scoping.

**Every query against a tenant-scoped table must filter on `hospital_id`.**

Conventions do not hold this. Somebody writes a read for a dashboard panel at
2am, forgets the filter, and one hospital's OPD sees another's. The failure is
silent, it looks like a working feature, and it is a reportable breach.

So it is enforced twice:

1. `TenantContext` is set from the authenticated principal for the life of a
   request. It is a `ContextVar`, so it survives across `await` boundaries and
   does not leak between concurrent requests.
2. A SQLAlchemy `do_orm_execute` listener inspects every ORM statement before it
   runs. A SELECT, UPDATE or DELETE touching a tenant-scoped table without a
   `hospital_id` predicate raises `MissingTenantFilter` — and the *statement
   fails*, rather than quietly returning another hospital's rows.

The listener is a backstop, not the mechanism. Repositories filter explicitly;
the listener is what catches the query that forgot to. `tests/safety/
test_tenancy.py` proves it fires.

When the deployment moves to a database per hospital, the filter becomes
redundant rather than wrong, and this module is what makes that a configuration
change instead of an audit.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session
from sqlalchemy.sql import Delete, Select, Update
from sqlalchemy.sql.elements import ColumnClause

from app.core.errors import MediKioskError
from app.models.clinical import TENANT_COLUMN, TENANT_EXEMPT_TABLES


class MissingTenantFilter(MediKioskError):
    """A query touched a tenant-scoped table without a `hospital_id` predicate.

    A 500, deliberately. There is no client input that should produce this — it
    is a bug in a repository, and it must be loud in development rather than
    subtle in production.
    """

    status_code = 500
    code = "missing_tenant_filter"

    def __init__(self, tables: frozenset[str]) -> None:
        super().__init__(
            "query touched tenant-scoped tables without a hospital_id filter: "
            f"{sorted(tables)}",
            details={"tables": sorted(tables)},
        )


class NoTenantContext(MediKioskError):
    """Tenant-scoped work was attempted with no hospital in context."""

    status_code = 500
    code = "no_tenant_context"

    def __init__(self) -> None:
        super().__init__(
            "no hospital is in scope for this operation; every clinical read and "
            "write is performed on behalf of exactly one hospital"
        )


@dataclass(frozen=True, slots=True)
class TenantContext:
    """The hospital a unit of work belongs to."""

    hospital_id: str


_current: ContextVar[TenantContext | None] = ContextVar("medikiosk_tenant", default=None)

#: Set while a deliberately cross-tenant operation runs — schema migration,
#: the tenant list itself, the seeder. Narrow, explicit and short-lived; there
#: is no request path that sets it.
_unscoped: ContextVar[bool] = ContextVar("medikiosk_tenant_unscoped", default=False)


def set_tenant(hospital_id: str) -> Token[TenantContext | None]:
    """Put a hospital in scope. Returns a token for `reset_tenant`."""
    return _current.set(TenantContext(hospital_id=hospital_id))


def reset_tenant(token: Token[TenantContext | None]) -> None:
    _current.reset(token)


def current_tenant() -> TenantContext | None:
    return _current.get()


def require_tenant() -> str:
    """The hospital in scope, or raise."""
    context = _current.get()
    if context is None:
        raise NoTenantContext()
    return context.hospital_id


@contextmanager
def tenant_scope(hospital_id: str) -> Iterator[TenantContext]:
    """Run a block on behalf of one hospital."""
    token = set_tenant(hospital_id)
    try:
        yield TenantContext(hospital_id=hospital_id)
    finally:
        reset_tenant(token)


@contextmanager
def unscoped() -> Iterator[None]:
    """Run a block without the tenant guard.

    For migrations, the seeder and the hospital registry itself. Deliberately
    ugly to type and deliberately absent from every request path — if this
    appears in a repository, that repository is wrong.
    """
    token = _unscoped.set(True)
    try:
        yield
    finally:
        _unscoped.reset(token)


def is_unscoped() -> bool:
    return _unscoped.get()


# --- the guard ---------------------------------------------------------------


def _tenant_tables(statement: Select[Any] | Update | Delete) -> frozenset[str]:
    """Tenant-scoped tables this statement touches.

    A SELECT can draw from several FROM entities; an UPDATE or a DELETE has one
    target table and **no** `get_final_froms`. Calling it on them raised inside
    the listener, so an unscoped UPDATE or DELETE against a scoped table failed
    with an `AttributeError` from the guard rather than with the
    `MissingTenantFilter` the guard exists to raise — the same request refused
    for the wrong reason, and an error nobody would read as a tenancy problem.
    """
    entities: list[object]
    if isinstance(statement, Select):
        entities = list(statement.get_final_froms())
    else:
        entities = [statement.table]

    names: set[str] = set()
    for entity in entities:
        name = getattr(entity, "name", None)
        if isinstance(name, str) and name not in TENANT_EXEMPT_TABLES:
            names.add(name)
    return frozenset(names)


def _filters_on_tenant(statement: Select[Any] | Update | Delete) -> bool:
    """True when `hospital_id` appears in the statement's WHERE clause.

    Structural: it walks the compiled criteria for a column named
    `hospital_id`, so it cannot be fooled by a filter that merely mentions the
    string. It does not check that the *value* is the current tenant — that is
    the repository's job, and the audit log's. What it catches is the absent
    filter, which is the failure that actually happens.
    """
    whereclause = getattr(statement, "whereclause", None)
    if whereclause is None:
        return False
    for element in whereclause.get_children(column_collections=False):
        if _mentions_tenant_column(element):
            return True
    return _mentions_tenant_column(whereclause)


def _mentions_tenant_column(element: object, depth: int = 0) -> bool:
    if depth > 12:  # a WHERE clause this deep is not one we can reason about
        return False
    if isinstance(element, ColumnClause) and element.name == TENANT_COLUMN:
        return True
    children = getattr(element, "get_children", None)
    if children is None:
        return False
    return any(
        _mentions_tenant_column(child, depth + 1)
        for child in children(column_collections=False)
    )


def guard(state: ORMExecuteState) -> None:
    """`do_orm_execute` listener. Raises rather than filtering.

    It refuses to silently *add* the missing filter, which some frameworks do.
    Auto-scoping teaches everyone that the filter is optional, and then one query
    runs through a path the auto-scoper does not cover.
    """
    if is_unscoped():
        return
    statement = state.statement
    if not isinstance(statement, Select | Update | Delete):
        return  # INSERT carries its tenant in the row, not in a predicate
    touched = _tenant_tables(statement)
    if not touched:
        return
    if not _filters_on_tenant(statement):
        raise MissingTenantFilter(touched)


def install(session_class: type[Session] | object = Session) -> None:
    """Install the guard. Idempotent; safe to call from tests."""
    if not event.contains(session_class, "do_orm_execute", guard):
        event.listen(session_class, "do_orm_execute", guard)


def uninstall(session_class: type[Session] | object = Session) -> None:
    """Remove the guard. Used only by the test that proves it was installed."""
    if event.contains(session_class, "do_orm_execute", guard):
        event.remove(session_class, "do_orm_execute", guard)
