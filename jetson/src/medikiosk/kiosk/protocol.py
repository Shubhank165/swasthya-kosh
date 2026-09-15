"""Replay protection for one locally owned patient journey.

An encounter identifier is public metadata, not permission to resume it. The
opaque capability stays with the tablet and the encrypted snapshot store.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections import OrderedDict
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class FlowAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["flow.action"]
    session_id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=0)
    action_id: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=40)
    value: Any = None
    question_id: str | None = Field(default=None, max_length=128)


class SessionGuard:
    """A socket lease owns this guard; touch and voice share its turn lock."""

    def __init__(self, session_id: str | None = None, token: str | None = None) -> None:
        self.session_id = session_id or str(uuid4())
        self.token = token or secrets.token_urlsafe(32)
        self.revision = 0
        self._accepted: OrderedDict[str, str] = OrderedDict()

    def check(self, action: FlowAction) -> bool:
        """Return False for an identical retry; reject conflicting/stale input."""
        if action.session_id != self.session_id:
            raise ValueError("Action belongs to a different session")
        fingerprint = self._fingerprint(action)
        prior = self._accepted.get(action.action_id)
        if prior is not None:
            if prior != fingerprint:
                raise ValueError("Action identifier was already used")
            return False
        if action.revision != self.revision:
            raise ValueError("The prompt changed; use the current screen")
        return True

    def accept(self, action: FlowAction) -> None:
        self._accepted[action.action_id] = self._fingerprint(action)
        self._accepted.move_to_end(action.action_id)
        while len(self._accepted) > 256:
            self._accepted.popitem(last=False)

    def invalidate_prompt(self) -> None:
        self.revision += 1

    def owns(self, session_id: str, token: str) -> bool:
        return session_id == self.session_id and secrets.compare_digest(token, self.token)

    def snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "revision": self.revision,
            "accepted": list(self._accepted.items()),
        }

    def restore(self, data: dict[str, Any]) -> None:
        if data.get("session_id") != self.session_id:
            raise ValueError("Snapshot belongs to a different session")
        self.revision = int(data["revision"]) + 1
        self._accepted = OrderedDict(data.get("accepted", [])[-256:])

    @staticmethod
    def _fingerprint(action: FlowAction) -> str:
        encoded = json.dumps(
            action.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
