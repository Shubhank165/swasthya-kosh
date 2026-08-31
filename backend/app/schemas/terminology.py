"""Terminology API DTOs."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import ApiModel


class TerminologyMatchOut(ApiModel):
    """One candidate. `mappings` is empty when no mapping exists — which is a
    real answer, not a gap for the client to fill in."""

    system: str
    code: str
    display: str
    score: float
    matched_on: str
    definition: str | None = None
    mappings: dict[str, dict[str, str]] = Field(default_factory=dict)


class TerminologySearchOut(ApiModel):
    query: str
    systems: list[str]
    results: list[TerminologyMatchOut] = Field(default_factory=list)
