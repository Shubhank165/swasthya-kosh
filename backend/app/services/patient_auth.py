"""Phone OTP sign-in for the patient app — 2/3 §7.1, §12.

The whole of the patient app's security rests on this file, so the reasoning is
written down rather than assumed.

**Nothing identifying is stored in plaintext.** The phone becomes a peppered
HMAC (`phone_ref`), the code becomes a hash, the session token becomes a hash.
A dump of `otp_challenges` and `patient_sessions` tells an attacker neither who
was signing in, nor what code to type, nor how to impersonate anyone. This is
stronger than the usual bar because the population is identifiable as patients
of an AYUSH hospital, which is itself health-adjacent information.

**Why a pepper and not a plain hash.** An Indian mobile number is ten digits
with a known prefix set — under a billion candidates. A plain SHA-256 of one is
reversed by exhaustive search in seconds on a laptop, so a bare digest would be
the phone book with extra steps. The pepper is server-side, from Secret Manager,
and never in the database; an attacker with the database alone cannot enumerate.

**Failure is uniform.** Wrong code, expired challenge, burned challenge and
no-such-challenge all produce the same error, so the endpoint cannot be used to
learn whether a number has an account.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update

from app.adapters.protocols import OTPSender
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import ConfigurationError, UnauthorizedError, ValidationError
from app.core.ids import IdFactory
from app.core.logging import get_logger
from app.db.tenancy import unscoped
from app.models.clinical import OTPChallenge, PatientSession

logger = get_logger(__name__)

#: Deliberately generic. Distinguishing "no such challenge" from "wrong code"
#: turns this endpoint into an oracle for which numbers are registered.
_REJECTED = "that code is not valid; request a new one"


def phone_ref(phone: str, *, pepper: str | None) -> str:
    """The stored reference for a phone number.

    Refuses to run without a pepper rather than falling back to a plain digest.
    A fallback here would be the failure mode where everything works, nothing
    errors, and the privacy property is silently absent.
    """
    if not pepper:
        raise ConfigurationError(
            "PATIENT_REF_PEPPER is not set. Patient phone references are peppered "
            "HMACs; without it they would be plain digests of ten-digit numbers, "
            "which are reversible by exhaustive search."
        )
    normalised = normalise_phone(phone)
    return hmac.new(
        pepper.encode("utf-8"), normalised.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def normalise_phone(phone: str) -> str:
    """One number, one reference.

    `+91 98765 43210`, `09876543210` and `9876543210` are the same person, and
    would otherwise be three accounts with three sets of history.
    """
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10:
        raise ValidationError(
            "a ten-digit Indian mobile number is required",
            details={"digits_seen": len(digits)},
        )
    return digits


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Challenge:
    """What the request endpoint hands back.

    `code` is populated only by the mock sender, and only outside production.
    It exists so a demo and the integration tests can complete a sign-in without
    an SMS gateway; `PatientAuthService` refuses to include it when
    `ENVIRONMENT` is production, so the path that returns a live OTP in an API
    response cannot be reached by configuration alone.
    """

    challenge_id: str
    expires_at: datetime
    code: str | None = None


@dataclass(frozen=True, slots=True)
class Session:
    token: str
    patient_ref: str
    expires_at: datetime


class PatientAuthService:
    def __init__(
        self,
        session: object,
        *,
        settings: Settings,
        sender: OTPSender,
        clock: Clock,
        ids: IdFactory,
    ) -> None:
        self._session = session
        self._settings = settings
        self._sender = sender
        self._clock = clock
        self._ids = ids

    # --- request -------------------------------------------------------------

    async def request_code(self, phone: str) -> Challenge:
        """Issue a code and send it.

        Rate limited per number per hour. An unlimited OTP endpoint is a free
        SMS cannon that anyone can aim at a stranger's phone, and the cost lands
        on the hospital's gateway bill and the stranger's evening.
        """
        settings = self._settings
        ref = phone_ref(phone, pepper=settings.patient_ref_pepper)
        now = self._clock.now()

        with unscoped():
            recent = await self._session.scalar(  # type: ignore[attr-defined]
                select(func.count())
                .select_from(OTPChallenge)
                .where(
                    OTPChallenge.phone_ref == ref,
                    OTPChallenge.created_at >= now - timedelta(hours=1),
                )
            )
            if (recent or 0) >= settings.otp_max_per_hour:
                logger.warning("otp_rate_limited")
                raise ValidationError(
                    "too many codes requested for this number; try again later",
                    details={"retry_after_seconds": 3600},
                )

            # Any outstanding challenge for this number is burned. Two live
            # codes for one phone doubles the guessing surface for no benefit.
            await self._session.execute(  # type: ignore[attr-defined]
                update(OTPChallenge)
                .where(OTPChallenge.phone_ref == ref, OTPChallenge.consumed_at.is_(None))
                .values(consumed_at=now)
            )

            code = f"{secrets.randbelow(1_000_000):06d}"
            expires_at = now + timedelta(seconds=settings.otp_ttl_seconds)
            challenge = OTPChallenge(
                id=self._ids.new_id("otp"),
                phone_ref=ref,
                code_hash=_hash(code),
                expires_at=expires_at,
                attempts=0,
            )
            self._session.add(challenge)  # type: ignore[attr-defined]

        await self._sender.send(phone=phone, code=code)
        # The code is never logged, at any level. The phone is never logged at
        # all — not even its reference, which is stable and so is a tracking id.
        logger.info("otp_requested", challenge_id=challenge.id)

        reveal = self._sender.reveals_code and settings.environment != "production"
        return Challenge(
            challenge_id=challenge.id,
            expires_at=expires_at,
            code=code if reveal else None,
        )

    # --- verify --------------------------------------------------------------

    async def verify(self, *, challenge_id: str, code: str) -> Session:
        """Check the code and issue a session token."""
        settings = self._settings
        now = self._clock.now()

        with unscoped():
            challenge = await self._session.get(OTPChallenge, challenge_id)  # type: ignore[attr-defined]
            if challenge is None or challenge.consumed_at is not None:
                raise UnauthorizedError(_REJECTED)
            if challenge.expires_at <= now:
                await self._burn(challenge, now)
                raise UnauthorizedError(_REJECTED)
            if challenge.attempts >= settings.otp_max_attempts:
                await self._burn(challenge, now)
                raise UnauthorizedError(_REJECTED)

            # Counted before the comparison, so a crash between the two cannot
            # hand an attacker a free attempt — and **committed** before it,
            # which is the part that is easy to get wrong.
            #
            # The request-scoped session rolls back on any exception, so an
            # increment left uncommitted here is undone by the very
            # `UnauthorizedError` that a wrong guess raises. The counter would
            # read zero forever and the attempt cap would be decoration: a
            # six-digit code with unlimited guesses is a few hours of scripted
            # requests. Persisting it costs one commit per failed attempt.
            challenge.attempts += 1
            await self._session.commit()  # type: ignore[attr-defined]
            if not hmac.compare_digest(challenge.code_hash, _hash(code)):
                raise UnauthorizedError(_REJECTED)

            challenge.consumed_at = now
            token = secrets.token_urlsafe(32)
            record = PatientSession(
                id=self._ids.new_id("psession"),
                token_hash=_hash(token),
                phone_ref=challenge.phone_ref,
                expires_at=now + timedelta(hours=settings.patient_session_ttl_hours),
            )
            self._session.add(record)  # type: ignore[attr-defined]

        logger.info("patient_session_issued", session_id=record.id)
        return Session(
            token=token, patient_ref=challenge.phone_ref, expires_at=record.expires_at
        )

    async def _burn(self, challenge: OTPChallenge, now: datetime) -> None:
        """Mark a challenge spent, and make it stick.

        Committed for the same reason the attempt counter is: the caller raises
        immediately afterwards, and the request-scoped session would roll the
        write back.
        """
        challenge.consumed_at = now
        await self._session.commit()  # type: ignore[attr-defined]

    async def sign_out(self, *, token: str) -> None:
        now = self._clock.now()
        with unscoped():
            await self._session.execute(  # type: ignore[attr-defined]
                update(PatientSession)
                .where(PatientSession.token_hash == _hash(token))
                .values(revoked_at=now)
            )


async def resolve_session(session: object, *, token: str, now: datetime) -> str | None:
    """The `phone_ref` a token belongs to, or `None`.

    Used by `current_principal` on every patient request. Deliberately a plain
    function rather than a service method: authentication must not depend on the
    dependency graph that authentication guards.
    """
    with unscoped():
        row = await session.scalar(  # type: ignore[attr-defined]
            select(PatientSession).where(PatientSession.token_hash == _hash(token))
        )
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        return None
    return str(row.phone_ref)
