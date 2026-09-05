"""Authentication and roles.

Five roles: `patient`, `kiosk`, `staff`, `physician`, `admin`.

**Every guard is wired through `Depends`.** A previous build annotated the
physician-only routes and never wired them, and the routes were open —
documented as protected, and not. `tests/api/test_roles.py` now enumerates every
route in the OpenAPI schema and asserts its required role, so the same mistake
fails the build rather than shipping.

Two authentication paths:

- **Patient session tokens** (`Authorization: Bearer <token>`), issued by the
  phone-OTP flow in `api/v1/patient_auth.py` for the patient app. A patient
  reaches their own records and nothing else — see `Role.PATIENT`.
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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.db import get_session
from app.services.patient_auth import resolve_session


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

    #: The patient, on their own phone. Narrower than the kiosk: it may submit
    #: its own intake and read its own history, and it may not read a worklist,
    #: a report, another patient's anything, or any clinical view. A phone is
    #: the least controlled device in the system and holds the fewest rights.
    PATIENT = "patient"
    KIOSK = "kiosk"
    STAFF = "staff"
    PHYSICIAN = "physician"
    ADMIN = "admin"


#: Roles that inherit another's access. `ADMIN` sees everything; a physician can
#: do anything staff can. A kiosk inherits nothing — deliberately.
#:
#: `PATIENT` inherits nothing and is inherited by nothing — deliberately, and
#: not symmetrically with `KIOSK`. Staff must not acquire a patient's rights by
#: implication, because "read this patient's own history" is scoped by *whose*
#: history it is, and a role hierarchy cannot express that. Staff read patient
#: data through the routes that name a patient explicitly and are audited.
_IMPLIED: dict[Role, frozenset[Role]] = {
    Role.ADMIN: frozenset({Role.ADMIN, Role.PHYSICIAN, Role.STAFF, Role.KIOSK}),
    Role.PHYSICIAN: frozenset({Role.PHYSICIAN, Role.STAFF}),
    Role.STAFF: frozenset({Role.STAFF}),
    Role.KIOSK: frozenset({Role.KIOSK}),
    Role.PATIENT: frozenset({Role.PATIENT}),
}


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is making the request, and for which hospital."""

    user_id: str
    role: Role
    hospital_id: str
    #: Set only for `Role.PATIENT`. The patient this session belongs to, from
    #: the session token and never from the request — a patient asking for
    #: someone else's history is asking with their own token, so the identity
    #: has to come from the credential.
    patient_ref: str | None = None

    def has_any(self, *roles: Role) -> bool:
        granted = _IMPLIED[self.role]
        return any(role in granted for role in roles)


def _clock() -> Clock:
    """The clock authentication reads. Injected in tests; real everywhere else."""
    return SystemClock()


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
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
    x_hospital_id: Annotated[str | None, Header(alias="X-Hospital-Id")] = None,
) -> Principal:
    """Identify the caller. Fails closed on anything it does not recognise."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

        # Kiosk tokens first: an in-memory map compared with `compare_digest`,
        # so the common case costs no query.
        hospital_id = _token_hospital(settings, token)
        if hospital_id is not None:
            return Principal(
                user_id=f"kiosk:{token[:8]}", role=Role.KIOSK, hospital_id=hospital_id
            )

        # Then a patient session. The hospital comes from the header rather than
        # the credential, because a patient may complete an intake for any
        # hospital they choose — the credential says *who*, not *where*. What it
        # cannot do is widen access: `patient_ref` is taken from the session and
        # never from the request, so a patient asking for a different patient's
        # history is still asking as themselves.
        patient_ref = await resolve_session(
            session, token=token, now=_clock().now()
        )
        if patient_ref is not None:
            if not x_hospital_id:
                raise UnauthorizedError(
                    "X-Hospital-Id is required; choose a hospital before continuing"
                )
            return Principal(
                user_id=f"patient:{patient_ref[:12]}",
                role=Role.PATIENT,
                hospital_id=x_hospital_id,
                patient_ref=patient_ref,
            )

        raise UnauthorizedError("unrecognised service token")

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
RequirePatient = Annotated[Principal, Depends(require_roles(Role.PATIENT))]
#: Ingest accepts all three: a kiosk in the corridor, a staff member at a
#: counter, or a patient on their own phone before they travel.
RequireIntakeSubmitter = Annotated[
    Principal, Depends(require_roles(Role.KIOSK, Role.STAFF, Role.PATIENT))
]
