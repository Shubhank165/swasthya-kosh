"""Identifier generation.

The domain never generates an id; the caller supplies one. This module is the
one place uuid4 is called, and `SequentialIdFactory` makes the whole system
reproducible under test.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4


class IdFactory(Protocol):
    def new_id(self, prefix: str = "") -> str: ...


class UuidIdFactory:
    """Production factory. Ids are UUID4 strings, optionally prefixed so a value
    is self-describing in a log line."""

    def new_id(self, prefix: str = "") -> str:
        value = str(uuid4())
        return f"{prefix}_{value}" if prefix else value


class SequentialIdFactory:
    """Deterministic factory for tests and the evaluation harness."""

    def __init__(self, start: int = 1) -> None:
        self._counter = start - 1

    def new_id(self, prefix: str = "") -> str:
        self._counter += 1
        stem = f"{self._counter:06d}"
        return f"{prefix}_{stem}" if prefix else stem


def is_uuid(value: str) -> bool:
    """True when `value` is a bare UUID, ignoring any prefix."""
    candidate = value.split("_", 1)[-1]
    try:
        UUID(candidate)
    except ValueError:
        return False
    return True
