"""Shared response shapes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    """Base for every DTO. Forbids unknown fields so a client typo is an error
    rather than a silently dropped answer."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ErrorResponse(ApiModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class Acknowledgement(ApiModel):
    ok: bool = True
    message: str | None = None
