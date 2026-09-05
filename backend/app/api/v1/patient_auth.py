"""Phone sign-in for the patient app — 2/3 §7.1, §12.

Thin routes over `PatientAuthService`, which is where the reasoning lives. Two
things about this router are worth stating here, because they are properties of
the *endpoints* rather than of the service:

**Both routes are unauthenticated**, necessarily — they are how a caller
acquires a credential. That makes them the only writable surface in this system
reachable with no token at all, which is why the service rate-limits per number
and why failures are uniform. `tests/api/test_roles.py` lists them among the
deliberately open routes.

**Neither route echoes the phone number back.** Not in a success body, not in an
error, not in a log line. An endpoint that confirms "we sent a code to
98765xxxxx" is an endpoint that confirms a number is real to whoever typed it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Response, status

from app.api.deps import PatientAuthServiceDep, ProvidersDep
from app.schemas.api import (
    OTPRequestBody,
    OTPRequestResponse,
    OTPVerifyBody,
    PatientSessionResponse,
)

router = APIRouter(prefix="/auth/otp", tags=["patient-auth"])


@router.post(
    "/request",
    response_model=OTPRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send a one-time code to a phone number",
)
async def request_code(
    service: PatientAuthServiceDep,
    providers: ProvidersDep,
    body: OTPRequestBody,
) -> OTPRequestResponse:
    """Issue a code.

    Always answers the same way for a well-formed number, whether or not that
    number has ever been seen. Telling a caller "no account for this number"
    would turn the endpoint into a membership oracle for patients of an AYUSH
    hospital.
    """
    challenge = await service.request_code(body.phone)
    return OTPRequestResponse(
        challenge_id=challenge.challenge_id,
        expires_at=challenge.expires_at.isoformat(),
        code=challenge.code,
        # Named out loud in every response, so a demo cannot present a mocked
        # delivery as a real SMS without the response saying otherwise.
        delivery=providers.otp.name,
    )


@router.post(
    "/verify",
    response_model=PatientSessionResponse,
    summary="Exchange a code for a patient session token",
)
async def verify(
    service: PatientAuthServiceDep, body: OTPVerifyBody
) -> PatientSessionResponse:
    """Check the code and issue a session.

    The token goes into the phone's Keychain or Keystore, never into shared
    preferences — 2/3 §7.1. The server stores only its hash.
    """
    session = await service.verify(challenge_id=body.challenge_id, code=body.code)
    return PatientSessionResponse(
        token=session.token,
        expires_at=session.expires_at.isoformat(),
        patient_ref=session.patient_ref,
    )


@router.post(
    "/sign-out",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke this patient session",
)
async def sign_out(
    service: PatientAuthServiceDep,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Response:
    """Revoke the presented token.

    Deliberately not role-guarded and deliberately always `204`. A sign-out that
    refuses an already-invalid token tells the caller whether it was valid, and
    an app clearing its own state on logout should not have to care either way —
    2/3 §10 requires it to wipe local storage regardless of what the server says.
    """
    if authorization and authorization.lower().startswith("bearer "):
        await service.sign_out(token=authorization[7:].strip())
    return Response(status_code=status.HTTP_204_NO_CONTENT)
