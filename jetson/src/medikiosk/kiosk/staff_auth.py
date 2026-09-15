"""Separate offline staff sessions. Patient capabilities never authorize staff routes."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request

COOKIE = "medikiosk_staff"
ITERATIONS = 600_000


def password_hash(password: str) -> str:
    """Provisioning utility; never writes or changes a credential file itself."""
    if len(password) < 12:
        raise ValueError("Use at least 12 characters")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or int(iterations) != ITERATIONS:
            return False
        if len(salt) != 32 or len(expected) != 64 or len(password) > 1024:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        )
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class StaffSession:
    identity: str
    csrf: str
    expires: float


class StaffAuth:
    def __init__(self, users_path: Path | None, allow_insecure_http: bool = False) -> None:
        self.users: dict[str, str] = {}
        if users_path is not None:
            path = users_path.expanduser()
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or path.is_symlink():
                raise ValueError("Staff credentials must be a regular private file")
            if os.name != "nt" and (info.st_mode & 0o077 or info.st_uid != os.getuid()):
                raise ValueError("Staff credential file must be owned by service user, mode 0600")
            data = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or not data
                or len(data) > 100
                or any(
                    not isinstance(k, str) or not k or len(k) > 100 or not isinstance(v, str)
                    for k, v in data.items()
                )
            ):
                raise ValueError("Invalid staff credential file")
            self.users = data
        self._lock = threading.Lock()
        self.allow_insecure_http = allow_insecure_http
        self.sessions: OrderedDict[str, StaffSession] = OrderedDict()
        self.attempts: list[float] = []
        self.dummy_hash = password_hash(secrets.token_urlsafe(24)) if self.users else ""

    def same_origin(self, request: Request) -> None:
        if request.headers.get("origin") != f"{request.url.scheme}://{request.url.netloc}":
            raise HTTPException(403, "Same-origin staff request required")
        if request.url.scheme != "https" and not self.allow_insecure_http:
            raise HTTPException(403, "HTTPS is required for staff authentication")

    def login(self, request: Request, username: str, password: str) -> tuple[str, StaffSession]:
        self.same_origin(request)
        if not self.users:
            raise HTTPException(503, "Offline staff access has not been provisioned")
        now = time.monotonic()
        with self._lock:
            self.attempts = [t for t in self.attempts if now - t < 60]
            if len(self.attempts) >= 10:
                raise HTTPException(429, "Wait before attempting staff sign-in again")
            self.attempts.append(now)
        valid = verify_password(password, self.users.get(username, self.dummy_hash))
        if not valid or username not in self.users:
            raise HTTPException(401, "Invalid staff sign-in")
        token = secrets.token_urlsafe(32)
        session = StaffSession(username, secrets.token_urlsafe(32), now + 1800)
        with self._lock:
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = session
            while len(self.sessions) > 100:
                self.sessions.popitem(last=False)
        return token, session

    def require(self, request: Request) -> StaffSession:
        token = request.cookies.get(COOKIE, "")
        key = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            session = self.sessions.get(key)
            if not session or session.expires <= time.monotonic():
                self.sessions.pop(key, None)
                raise HTTPException(401, "Staff sign-in required")
        if request.method not in {"GET", "HEAD"}:
            self.same_origin(request)
            if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), session.csrf):
                raise HTTPException(403, "Staff CSRF token required")
        return session

    def logout(self, request: Request) -> None:
        self.require(request)
        with self._lock:
            self.sessions.pop(hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest(), None)
