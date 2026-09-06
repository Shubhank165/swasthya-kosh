"""Kiosk input contracts, by schema version.

**The registry lives here, and there is exactly one of it.**

There used to be two. `app/normalize/registry.py` mapped a version to its
normalizer and this mapping lived, separately, in `app/services/repair.py` —
so registering 0.2 in one and not the other left the backend able to *normalise*
a 0.2 payload it would never accept, because validation ran first and refused
the version. The Flutter app had been sending 0.2 for a while; every intake it
submitted was stored raw as `needs_manual_review`, and ingest answers an
unparseable payload with a 200 by design, so nothing failed and nobody noticed
until the app's live end-to-end test tried to upload a document to an intake
that did not exist.

`tests/contracts/test_normalizer_registry.py` now asserts the two registries
have identical keys, so the next version cannot be half-registered.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.contracts.kiosk.v0_1 import KioskIntakeV0_1
from app.contracts.kiosk.v0_2 import KioskIntakeV0_2

#: Contract model per schema version. Adding a version means adding a line here
#: and a line in `app/normalize/registry.py`, and the test above proves both
#: happened.
CONTRACTS: dict[str, type[BaseModel]] = {
    "0.1": KioskIntakeV0_1,
    "0.2": KioskIntakeV0_2,
}


def contract_for(version: object) -> type[BaseModel] | None:
    """The contract for `version`, or `None` if this build has none."""
    return CONTRACTS.get(version) if isinstance(version, str) else None


def supported_contract_versions() -> tuple[str, ...]:
    return tuple(sorted(CONTRACTS))


__all__ = [
    "CONTRACTS",
    "KioskIntakeV0_1",
    "KioskIntakeV0_2",
    "contract_for",
    "supported_contract_versions",
]
