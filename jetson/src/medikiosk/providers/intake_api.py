"""Client for the hospital intake API - the only path by which a document leaves the kiosk.

Two calls matter here and they have opposite retry semantics, which is the whole reason this is a
module rather than three lines of urllib at the call site:

  POST /api/v1/intakes/ingest                     idempotent, keyed by Idempotency-Key.
                                                  Retry freely; the same key returns the original
                                                  intake and creates nothing.

  POST /api/v1/intakes/{id}/documents             NOT idempotent. A retry after an ambiguous
                                                  timeout creates a SECOND document on the
                                                  patient's record, and nothing upstream will
                                                  merge them.

So every send is classified by whether the request could possibly have reached the server:

  Unreachable  DNS failure, connection refused, TLS failure - the bytes never left. Safe to retry.
  Ambiguous    the connection was established and then timed out or dropped. The server may have
               accepted it. Never retried; the caller records it and a human decides.
  Answered     an HTTP status came back. The outcome is known, whatever it is.

Getting that distinction wrong duplicates clinical documents on a patient's record, so it is
modelled explicitly rather than left to `except Exception`.

The token is a static bearer string bound to a hospital in Secret Manager, and that binding is
authoritative - a device physically cannot write into another hospital's records. It is read from
a root-only file or the environment, never committed, and never logged: `redacted()` exists so
that a debug line cannot print it by accident.
"""

from __future__ import annotations

import json
import mimetypes
import os
import socket
import ssl
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://medikiosk-api-tjynzes4vq-el.a.run.app"

# Document kinds the API accepts. Anything else is sent as "other" rather than rejected locally -
# a mislabelled document still belongs on the record.
KINDS = ("prescription", "lab_report", "discharge_summary", "other")

# The kiosk contract version ingest understands. Anything without it is filed as unusable - the
# API returns intake_id: null and reason: unsupported_version, and nothing can be attached to it.
SCHEMA_VERSION = "0.2"


def kiosk_envelope(report: dict[str, Any], intake_id: str) -> dict[str, Any]:
    """Wrap the kiosk's report in the shape ingest accepts.

    The kiosk chooses its own intake_id (a UUID) and the API echoes it back, which is what lets a
    document scanned at stage 7 be addressed to an intake that only gets ingested at stage 9.

    Only *bound* values go in `fields`. The API's contract separates a field that was answered
    from one that never was, and refuses a payload that carries a value for an unresolved field -
    which is exactly what sending our `not_established` list did: the names of the questions the
    patient never answered, delivered as if they were an answer. Found against the live deploy
    as `repair_failed`. Our own report keeps that distinction too; it just spells it differently:

        clinical.complaint / duration / severity   bound scalars
        clinical.findings                          bound yes/no answers, keyed by field
        clinical.medications / allergies           bound lists, meaningful only when non-empty
        clinical.not_established                   the unresolved names - metadata, never sent

    generated_at is not sent either: the API rejects it outright, presumably because that is a
    timestamp it sets, not one it accepts.

    The authoritative shape is the backend's tests/fixtures/kiosk/0.2.json, which this side does
    not have. What is sent here is accepted (`status: partial`) and creates a real intake that
    documents can attach to; the API maps the names it recognises and flags the rest for review.
    """

    clinical = report.get("clinical") or {}
    patient = report.get("patient") or {}
    routing = report.get("routing") or {}

    fields: dict[str, Any] = {}
    for key in ("complaint", "duration", "severity"):
        if clinical.get(key) is not None:
            fields[key] = clinical[key]
    fields.update(clinical.get("findings") or {})
    for key in ("medications", "allergies"):
        if clinical.get(key):
            fields[key] = list(clinical[key])
    for key, value in (
        ("language", patient.get("language")),
        ("reported_by", patient.get("reported_by")),
        ("abha_last4", patient.get("abha_last4")),
        ("queue", routing.get("queue")),
        ("priority", routing.get("priority")),
    ):
        if value is not None:
            fields[key] = value
    raised = [flag.get("rule_id") for flag in report.get("red_flags") or [] if flag.get("rule_id")]
    if raised:
        fields["red_flags"] = raised

    return {"schema_version": SCHEMA_VERSION, "intake_id": intake_id, "fields": fields}


class Outcome(str, Enum):
    """Whether the request reached the server, which decides whether a retry is safe."""

    OK = "ok"
    UNREACHABLE = "unreachable"  # never left the building; retry is safe
    AMBIGUOUS = "ambiguous"  # may have been accepted; retry would duplicate
    REJECTED = "rejected"  # the server answered with an error; outcome is known


@dataclass(frozen=True)
class Response:
    outcome: Outcome
    status: int | None = None
    body: dict[str, Any] | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome is Outcome.OK

    @property
    def safe_to_retry(self) -> bool:
        """Only when the request provably never arrived.

        REJECTED is deliberately excluded: the server answered, so a retry is a new attempt at
        something already known to have failed, and for the non-idempotent document endpoint a
        4xx that was actually applied would duplicate.
        """

        return self.outcome is Outcome.UNREACHABLE


def redacted(token: str) -> str:
    """A token rendered safe to print. Never log the real one."""

    if not token:
        return "<none>"
    return f"<token:{len(token)} chars ending {token[-4:]}>"


def load_token(path: str | Path) -> str | None:
    """Read the kiosk token from its file, or None if this kiosk has not been provisioned.

    None is a normal state, not an error: a kiosk without a token simply keeps every document on
    the Jetson, which is the offline behaviour it had before any of this existed.

    A token file that group or others can read is refused outright rather than used. The token is
    a credential for a hospital's patient records with no expiry, and failing loudly at startup is
    much better than working quietly while anyone with a shell on the box can copy it. The error
    names the file and its mode - never the token.
    """

    token_path = Path(path).expanduser()
    try:
        info = token_path.stat()
    except FileNotFoundError:
        return None
    # Windows has no group/other bits for chmod to set, so the check only means something on the
    # POSIX box that actually runs the kiosk.
    if os.name == "posix" and info.st_mode & 0o077:
        raise PermissionError(
            f"{token_path} is readable beyond its owner (mode {oct(info.st_mode & 0o777)}); "
            f"run: chmod 600 {token_path}"
        )
    token = token_path.read_text(encoding="ascii").strip()
    return token or None


class IntakeApi:
    def __init__(
        self,
        token: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        opener: Any = None,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Injected in tests so the retry taxonomy can be exercised without a network.
        self._opener = opener or urllib.request.urlopen

    # ------------------------------------------------------------------ transport

    def _send(self, request: urllib.request.Request) -> Response:
        request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with self._opener(request, timeout=self.timeout) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            # The server answered. Whatever it said, the outcome is not in doubt.
            body = _parse(error.read())
            return Response(Outcome.REJECTED, error.code, body, str(body or error.reason))
        except urllib.error.URLError as error:
            reason = error.reason
            if isinstance(reason, socket.timeout | TimeoutError):
                # Connected, then no answer. The server may already have accepted it.
                return Response(Outcome.AMBIGUOUS, detail="timed out awaiting a response")
            if isinstance(reason, ConnectionResetError | BrokenPipeError):
                return Response(Outcome.AMBIGUOUS, detail=f"connection dropped: {reason}")
            if isinstance(reason, socket.gaierror | ConnectionRefusedError | ssl.SSLError):
                return Response(Outcome.UNREACHABLE, detail=f"never connected: {reason}")
            # An unrecognised transport failure could be either. Assume the dangerous one.
            return Response(Outcome.AMBIGUOUS, detail=f"transport failure: {reason}")
        except TimeoutError as error:
            return Response(Outcome.AMBIGUOUS, detail=f"timed out: {error}")

        return Response(Outcome.OK, status, _parse(raw))

    # ------------------------------------------------------------------ calls

    def whoami(self) -> Response:
        """Provisioning smoke test. 200 proves the token is real and names its hospital.

        The obvious-looking check - GET /api/v1/content/bundle - returns 200 with no header at all
        and 200 with a garbage token, so it proves nothing about provisioning. This endpoint 401s
        on both.
        """

        return self._send(urllib.request.Request(f"{self.base_url}/api/v1/kiosk/whoami"))

    def ingest(self, record: dict[str, Any], idempotency_key: str | None = None) -> Response:
        """Submit the completed intake. Safe to retry with the same key - that is its point."""

        request = urllib.request.Request(
            f"{self.base_url}/api/v1/intakes/ingest",
            data=json.dumps(record, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key or str(uuid.uuid4()),
            },
            method="POST",
        )
        return self._send(request)

    def upload_document(self, intake_id: str, image: Path, kind: str = "other") -> Response:
        """Send one image for the cloud reader. NOT idempotent - see the module docstring.

        A caller that retries this after an AMBIGUOUS result puts a second copy of the same
        document on the patient's record.
        """

        if kind not in KINDS:
            kind = "other"
        body, content_type = _multipart(image, kind)
        request = urllib.request.Request(
            f"{self.base_url}/api/v1/intakes/{intake_id}/documents",
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )
        return self._send(request)

    def post_results(self, intake_id: str, extraction: dict[str, Any]) -> Response:
        """Path B: the Jetson read it, so only the extracted text travels - the image stays here."""

        request = urllib.request.Request(
            f"{self.base_url}/api/v1/intakes/{intake_id}/documents/results",
            data=json.dumps(extraction, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return self._send(request)


# ---------------------------------------------------------------------- helpers


def _parse(raw: bytes | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _multipart(image: Path, kind: str) -> tuple[bytes, str]:
    """Build a multipart body by hand rather than adding an HTTP library to an offline kiosk."""

    boundary = f"----medikiosk{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
    sep = f"--{boundary}\r\n".encode()
    parts = [
        sep,
        b'Content-Disposition: form-data; name="kind"\r\n\r\n',
        kind.encode("utf-8"),
        b"\r\n",
        sep,
        f'Content-Disposition: form-data; name="file"; filename="{image.name}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(),
        image.read_bytes(),
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"
