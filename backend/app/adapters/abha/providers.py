"""ABHA identity providers.

Two implementations, and the important thing about both is that neither pretends
to be live.

**`MockABHAProvider` stamps `"source": "mock"` on every response**, and the API
passes that through to the dashboard and the demo. A mocked government
integration presented as a working one is a lie told to a judging panel, and it
is the kind of lie that gets found out during questions.

`SandboxABHAProvider` is the shape of the real thing — an ABDM sandbox call —
and refuses to construct without credentials rather than falling back to the
mock. A silent fallback is how a demo ends up claiming a live ABDM link it does
not have.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.core.config import Settings
from app.core.errors import MediKioskError
from app.core.logging import get_logger

logger = get_logger(__name__)

#: `name@sbx`, `name@abdm`. A handle, not a secret — unlike the 14-digit ABHA
#: *number*, which this system neither asks for nor stores.
ABHA_ADDRESS = re.compile(r"^[a-z0-9][a-z0-9._-]{2,}@[a-z]{2,10}$", re.IGNORECASE)


class ABHAUnavailable(MediKioskError):
    """The ABHA provider could not be reached or was not configured."""

    status_code = 503
    code = "abha_unavailable"


def is_wellformed(abha_address: str) -> bool:
    """True when `abha_address` has the shape of an ABHA address.

    Shape only. It says nothing about whether the address exists, and the API
    must never present a well-formed address as a verified one.
    """
    return bool(ABHA_ADDRESS.match(abha_address.strip()))


class MockABHAProvider:
    """Deterministic fixtures. Visibly a mock, by design.

    Verification is derived from a hash of the address, so the same address
    always gives the same answer and a demo is reproducible — and roughly one
    address in eight comes back unverified, so the not-found path is on screen
    rather than theoretical.
    """

    name = "mock"

    async def verify(self, abha_address: str) -> dict[str, Any] | None:
        address = abha_address.strip()
        if not is_wellformed(address):
            return None
        digest = hashlib.sha256(address.encode("utf-8")).digest()
        if digest[0] % 8 == 0:
            return None
        return {
            # Every field a caller might key off says this is not real data.
            "source": "mock",
            "verified": True,
            "abha_address": address,
            "linked_care_contexts": 0,
            "notice": (
                "Mock ABHA response. No ABDM call was made and no government "
                "system was contacted."
            ),
        }


class SandboxABHAProvider:
    """ABDM sandbox.

    Stubbed until credentials arrive. It is wired far enough that turning it on
    is a configuration change, and it raises rather than degrading, so an
    unconfigured deployment cannot quietly serve mock data under a live label.
    """

    name = "sandbox"

    def __init__(self, settings: Settings) -> None:
        if not settings.abdm_base_url:
            raise ABHAUnavailable(
                "ABDM_BASE_URL is not set. The sandbox provider will not fall back "
                "to the mock: a mocked government integration must never be served "
                "under a live label."
            )
        self._base_url = settings.abdm_base_url

    async def verify(self, abha_address: str) -> dict[str, Any] | None:
        raise ABHAUnavailable(
            "the ABDM sandbox integration is not wired in this build; "
            "ABHA_PROVIDER=mock is the supported configuration"
        )


def build_provider(settings: Settings) -> MockABHAProvider | SandboxABHAProvider:
    """The configured provider."""
    if settings.abha_provider == "sandbox":
        return SandboxABHAProvider(settings)
    return MockABHAProvider()
