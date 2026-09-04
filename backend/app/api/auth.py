"""Authentication and roles.

Four roles: `kiosk`, `staff`, `physician`, `admin`.

**Every guard is wired through `Depends`.** A previous build annotated the
physician-only routes and never wired them, and the routes were open —
documented as protected, and not. `tests/api/test_roles.py` now enumerates every
route in the OpenAPI schema and asserts its required role, so the same mistake
fails the build rather than shipping.

Two authentication paths:

- **Kiosk tokens** (`Authorization: Bearer <token>`). A kiosk's token is bound to
  exactly one `hospital_id`, and that binding — not the request body — decides
  which hospital the intake belongs to. A device claiming otherwise is
  misconfigured at best.
- **Header principals** (`X-User-Id` / `X-User-Role` / `X-Hospital-Id`), a
  stand-in for the hospital's identity provider while the dashboard is built.
  Gated on `ALLOW_HEADER_AUTH`, which is off in any environment holding real
  data. Turning it off there is the deployment's job; refusing to start without
  it configured is this module's.

Swapping in the hospital's real IdP changes this file and nothing else.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError


def auth_settings() -> Settings:
    """Settings, as a dependency.

    Injected rather than read, so the identity configuration a request is
    authenticated against is the one the application was built with — and so a
    test can substitute it without reaching into a module global.
    """
    return get_settings()


class Role(StrEnum):
    """Who is calling.

    `KIOSK` is the device. It can submit an intake and upload a document; it
    cannot read a report, cannot see the worklist and cannot acknowledge an
    alert. A kiosk in a waiting room is physically accessible to anyone standing
    next to it, so it holds the narrowest set of permissions in the system.
    """

    KIOSK = "kiosk"
    STAFF = "staff"
    PHYSICIAN = "physician"
    ADMIN = "admin"


#: Roles that inherit another's access. `ADMIN` sees everything; a physician can
#: do anything staff can. A kiosk inherits nothing — deliberately.
_IMPLIED: dict[Role, frozenset[Role]] = {
    Role.ADMIN: frozenset({Role.ADMIN, Role.PHYSICIAN, Role.STAFF, Role.KIOSK}),
    Role.PHYSICIAN: frozenset({Role.PHYSICIAN, Role.STAFF}),
    Role.STAFF: frozenset({Role.STAFF}),
    Role.KIOSK: frozenset({Role.KIOSK}),
}


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is making the request, and for which hospital."""

    user_id: str
    role: Role
    hospital_id: str

    def has_any(self, *roles: Role) -> bool:
        granted = _IMPLIED[self.role]
        return any(role in granted for role in roles)


def _token_hospital(settings: Settings, token: str) -> str | None:
    """The hospital a kiosk token belongs to, or `None`.

    Compared with `compare_digest` so the lookup does not leak token contents
    through timing. The map is small; the comparison is the point.
    """
    for candidate, hospital_id in settings.kiosk_tokens.items():
        if hmac.compare_digest(candidate, token):
            return hospital_id
    return None


async def current_principal(
    settings: Annotated[Settings, Depends(auth_settings)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
    x_hospital_id: Annotated[str | None, Header(alias="X-Hospital-Id")] = None,
) -> Principal:
    """Identify the caller. Fails closed on anything it does not recognise."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        hospital_id = _token_hospital(settings, token)
        if hospital_id is None:
            raise UnauthorizedError("unrecognised service token")
        return Principal(
            user_id=f"kiosk:{token[:8]}", role=Role.KIOSK, hospital_id=hospital_id
        )

    if not settings.allow_header_auth:
        raise UnauthorizedError(
            "a service token is required; header authentication is disabled in "
            "this environment"
        )

    if not x_user_id or not x_user_role or not x_hospital_id:
        raise UnauthorizedError(
            "X-User-Id, X-User-Role and X-Hospital-Id headers are required"
        )
    try:
        role = Role(x_user_role)
    except ValueError as exc:
        # An unknown role fails closed rather than landing somewhere permissive.
        raise UnauthorizedError(f"unknown role {x_user_role!r}") from exc
    return Principal(user_id=x_user_id, role=role, hospital_id=x_hospital_id)


PrincipalDep = Annotated[Principal, Depends(current_principal)]


def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    """Dependency factory enforcing role membership.

    Used on every route. `tests/api/test_roles.py` asserts that no route escapes
    it, because a route that forgot is a route that is open.
    """

    def _check(principal: PrincipalDep) -> Principal:
        if not principal.has_any(*roles):
            raise ForbiddenError(
                f"role {principal.role.value!r} may not perform this action",
                details={"required": [r.value for r in roles]},
            )
        return principal

    return _check


#: Named guards, so a route declares its access in its signature and the role
#: test can read it back out of the dependency tree.
RequireKiosk = Annotated[Principal, Depends(require_roles(Role.KIOSK))]
RequireStaff = Annotated[Principal, Depends(require_roles(Role.STAFF))]
RequirePhysician = Annotated[Principal, Depends(require_roles(Role.PHYSICIAN))]
RequireAdmin = Annotated[Principal, Depends(require_roles(Role.ADMIN))]
#: Ingest and document upload: the kiosk, or a staff member entering on a
#: patient's behalf at a counter.
RequireKioskOrStaff = Annotated[Principal, Depends(require_roles(Role.KIOSK, Role.STAFF))]
