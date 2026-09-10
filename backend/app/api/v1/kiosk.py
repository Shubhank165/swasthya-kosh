"""Kiosk credential check — §12, §13.9.

One authenticated GET whose only job is to answer "is this token good, and for
which hospital". A device being provisioned in the field needs a call that
*fails* on a bad token — `GET /content/bundle` is deliberately open and returns
200 to anyone, so it cannot tell a working credential from a typo. This can.

Nothing here touches patient data: it reads back the principal the gateway
already resolved from the bearer token and nothing else.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.auth import RequireKiosk
from app.schemas.api import KioskIdentityOut

router = APIRouter(prefix="/kiosk", tags=["kiosk"])


@router.get(
    "/whoami",
    response_model=KioskIdentityOut,
    summary="Confirm a kiosk token and report the hospital it is bound to",
)
async def whoami(principal: RequireKiosk) -> KioskIdentityOut:
    """200 with the bound hospital for a valid kiosk token; 401 for a missing or
    unrecognised one; 403 for a token of the wrong role (a patient session, or
    a header-auth principal that is not `kiosk`).

    The `hospital_id` is the one the token is registered against in Secret
    Manager, which is authoritative — it is the value that will scope every
    upload the device makes, regardless of what the device puts in a request.
    """
    return KioskIdentityOut(
        role=principal.role.value,
        hospital_id=principal.hospital_id,
        user_id=principal.user_id,
    )
