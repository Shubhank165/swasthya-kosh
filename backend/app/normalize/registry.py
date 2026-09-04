"""Version dispatch.

**This is the file §4.2 promises stays one line per version.** Adding kiosk
schema 0.2 is:

1. `app/contracts/kiosk/v0_2.py`
2. `app/normalize/from_kiosk_v0_2.py`
3. one entry below

Nothing else changes. If a 0.2 field has no home in the canonical record, that
is the only case where `app/domain/record.py` changes — and then it is an
additive optional field, never a rename.

`tests/contracts/test_normalizer_registry.py` iterates this dict against golden
fixtures, so a version registered without one fails the suite.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from app.core.errors import MediKioskError
from app.domain.record import CanonicalRecord
from app.normalize import from_kiosk_v0_1


class UnsupportedSchemaVersion(MediKioskError):
    """The payload names a `schema_version` this build has no normalizer for.

    A 422 rather than a 400: the payload is well-formed, we simply cannot map
    it. The raw body is still stored, so an intake taken on a device running
    ahead of the backend is recoverable once the normalizer ships.
    """

    status_code = 422
    code = "unsupported_schema_version"

    def __init__(self, version: object) -> None:
        super().__init__(
            f"no normalizer registered for schema_version {version!r}",
            details={"schema_version": version, "supported": sorted(NORMALIZERS)},
        )


class Normalizer(Protocol):
    """A pure mapping from one input version to the canonical record.

    `now` is passed in rather than read, so every normalizer stays a pure
    function and every golden fixture stays reproducible.
    """

    def __call__(
        self, payload: Mapping[str, Any], *, now: datetime
    ) -> CanonicalRecord: ...


NORMALIZERS: dict[str, Normalizer] = {
    "0.1": from_kiosk_v0_1.normalize,
    # "0.2": from_kiosk_v0_2.normalize,
}


def supported_versions() -> tuple[str, ...]:
    return tuple(sorted(NORMALIZERS))


def normalizer_for(version: object) -> Normalizer:
    """The normalizer for `version`, or raise."""
    if not isinstance(version, str) or version not in NORMALIZERS:
        raise UnsupportedSchemaVersion(version)
    return NORMALIZERS[version]


def normalize(payload: Mapping[str, Any], *, now: datetime) -> CanonicalRecord:
    """Detect the version and dispatch.

    Raises `UnsupportedSchemaVersion` for an unknown version, and
    `pydantic.ValidationError` when the payload fails its own contract — the
    caller routes the latter to repair (§5.1).
    """
    return normalizer_for(payload.get("schema_version"))(payload, now=now)
