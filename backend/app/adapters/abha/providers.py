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
import json
import re
from pathlib import Path
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

    Two behaviours, and the second is the older one kept deliberately.

    A **known** address — one in `fixtures/mock_directory.json` — comes back
    with the invented person behind it, so the demo can show a returning
    patient rather than an address being typed into a box. Every one of those
    blocks carries `synthetic: true`.

    An **unknown** address falls back to the original hash rule: the same
    address always gives the same answer, and roughly one in eight comes back
    unverified. That path is kept precisely because fixtures would otherwise
    make the not-found case theoretical, and "this ABHA could not be verified,
    carry on as a guest" is a state the demo has to be able to show.

    `source` stays `"mock"` throughout. The app keys `isMocked` off that field,
    and §56 is that a mocked government integration is never presented as a
    live one.
    """

    name = "mock"

    #: Never varies by fixture. The app reads this, not the notice text.
    NOTICE = (
        "Mock ABHA response. No ABDM call was made and no government "
        "system was contacted."
    )

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._directory = _load_directory(fixtures_dir)

    async def verify(self, abha_address: str) -> dict[str, Any] | None:
        address = abha_address.strip()
        if not is_wellformed(address):
            return None

        entry = self._directory.get(address.lower())
        if entry is None:
            digest = hashlib.sha256(address.encode("utf-8")).digest()
            if digest[0] % 8 == 0:
                return None

        body: dict[str, Any] = {
            # Every field a caller might key off says this is not real data.
            "source": "mock",
            "verified": True,
            "abha_address": address,
            "linked_care_contexts": 0,
            "notice": self.NOTICE,
        }
        if entry is not None:
            # `synthetic` is re-asserted here rather than trusted from the file,
            # so an entry that forgot it still cannot read as a real person.
            body["demographics"] = {**entry, "synthetic": True}
        return body


def _load_directory(fixtures_dir: Path | None) -> dict[str, dict[str, Any]]:
    """The invented people, keyed by lowercased address.

    A missing or unreadable file is not an error: the provider falls back to
    hash-derived answers, which is exactly what it did before fixtures existed.
    Failing to start because a demo fixture is absent would be the wrong trade.
    """
    if fixtures_dir is None:
        return {}
    path = Path(fixtures_dir) / "mock_directory.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.info("abha_mock_directory_absent", path=str(path))
        return {}
    entries = raw.get("entries", {})
    if not isinstance(entries, dict):
        return {}
    return {str(key).lower(): dict(value) for key, value in entries.items()}


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
    return MockABHAProvider(settings.abha_fixtures_dir)
