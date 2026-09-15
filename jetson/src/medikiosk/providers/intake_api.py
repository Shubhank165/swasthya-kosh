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


# Our report's names for the answers, in the ids the backend's section table already lists as
# "exact field ids the Jetson's extractor is known to emit" - so they file under the right
# heading on the physician's sheet instead of falling through to History of Present Illness.
FIELD_IDS: dict[str, str] = {
    "complaint": "chief_complaint",
    "duration": "duration",
    "severity": "severity",
    "age_years": "age",
    "medications": "current_medications",
    "allergies": "allergy",
    "fever": "screen_fever",
    "vomiting": "screen_vomiting",
    "breathlessness": "breathlessness",
    "chest_pain": "chest_pain",
    "pain_radiation": "radiation",
    "sweating": "screen_sweating",
    "active_bleeding": "bleeding",
    "altered_consciousness": "altered_sensorium",
    "one_sided_weakness": "screen_one_sided_weakness",
    "speech_difficulty": "screen_speech_difficulty",
}

# What the patient never answered. `unresolved` is the contract's word for it, and a field in
# that state must carry no value - saying "we asked and got nothing" is the entire point.
UNRESOLVED = "unresolved"
ANSWERED = "answered"


def _outcome(value: Any, language: str | None, original: str | None = None) -> dict[str, Any]:
    """One field outcome in the contract's shape."""

    field: dict[str, Any] = {"status": ANSWERED, "value": value}
    if original and original != value:
        field["original_text"] = original
    if language:
        field["language"] = language
    return field


# The Ayurveda answers, under ids the backend files in its AYURVEDA section (an `ayurveda_`
# prefix, or the exact id `prakriti_self_report`). Our own names are kept rather than mapped
# onto agni/koshtha/nidra/mala/mutra: those are specific classical parameters, and claiming we
# asked about Koshtha because we asked about appetite would put a finding on a physician's
# sheet that no question established.
AYURVEDA_FIELDS = ("ahara_shakti", "vyayama_shakti", "satva", "satmya")


def _ayurveda_fields(report: dict[str, Any], language: str | None) -> dict[str, dict[str, Any]]:
    """What the Dashavidha and Prakriti questionnaires found, if either was run.

    Prakriti is sent as `prakriti_self_report` - self-report is what it is. It stays provisional
    until a vaidya signs off the item weights, and `scoring_reviewed` travels with it so the
    hospital cannot mistake a kiosk tally for a clinician's classification. Answers that did not
    support a Prakriti are sent as `unresolved`, not as an absent field: the patient sat through
    the instrument, and a record that omits it cannot be told apart from one never asked.
    """

    fields: dict[str, dict[str, Any]] = {}
    ayurveda = report.get("ayurveda") or {}
    prakriti = report.get("prakriti") or {}

    for name in AYURVEDA_FIELDS:
        if ayurveda.get(name) is not None:
            fields[f"ayurveda_{name}"] = _outcome(ayurveda[name], language)
    if ayurveda.get("prakriti_tendency"):
        fields["ayurveda_dosha_tendency"] = _outcome(ayurveda["prakriti_tendency"], language)

    if prakriti:
        name = prakriti.get("prakriti")
        if name:
            entry = _outcome(name, language)
            entry["scoring_reviewed"] = bool(prakriti.get("scoring_reviewed"))
            entry["answered"] = prakriti.get("answered")
            entry["asked_total"] = prakriti.get("asked_total")
            # A qualifier on this reading, not a finding of its own. Sent as an attribute so a
            # renderer that prints one bullet per field cannot turn "Provisional: item weights
            # are reconstructed..." into a line that reads as something found in the patient.
            if prakriti.get("note"):
                entry["note"] = prakriti["note"]
            fields["prakriti_self_report"] = entry
        else:
            fields["prakriti_self_report"] = {"status": UNRESOLVED}
    return fields


def _turns(report: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Every question asked, and which turn bound each field.

    Without this a physician clicking a line on the hospital's sheet gets nothing to check it
    against - the record validates, and is unverifiable. Superseded answers are sent too: a
    value the patient corrected is part of how the final one came to be, and the contract
    carries the whole history rather than only the survivor.

    Voice fields are sent as explicit nulls rather than omitted, matching what the hospital's
    own app sends, so one shape reaches the normalizer from both clients. A tapped answer has
    no transcript and says so; claiming the option label was a transcript would put words in
    the patient's mouth.
    """

    turns: list[dict[str, Any]] = []
    source: dict[str, int] = {}
    for entry in report.get("answer_history") or []:
        spoken = entry.get("method") == "voice"
        bound = _bound_field(entry)
        turns.append(
            {
                "turn_id": entry.get("turn"),
                "question_id": entry.get("id"),
                "asked_text": entry.get("question") or None,
                "transcript": (entry.get("answer") or None) if spoken else None,
                "asr_confidence": None,
                "bound_field": bound,
                "bound_value": entry.get("value"),
                "resolved": entry.get("status") == "answered",
                "language": entry.get("language"),
            }
        )
        if bound and not entry.get("superseded") and entry.get("turn") is not None:
            source[bound] = entry["turn"]
    return turns, source


def _bound_field(entry: dict[str, Any]) -> str | None:
    """Which key in `fields` this turn answered, or None when it answered no single field.

    The 58 Prakriti items are the honest None: they are scored together into one constitution,
    so no single item is the source of it.
    """

    question_id = entry.get("id") or ""
    if question_id.startswith("registration."):
        return FIELD_IDS.get(f"{question_id.split('.', 1)[1]}_years")
    field = entry.get("field")
    return FIELD_IDS.get(field) if field else None


def kiosk_envelope(
    report: dict[str, Any],
    intake_id: str,
    *,
    hospital_id: str,
    status: str = "complete",
    kiosk_id: str | None = None,
    engine_version: str | None = None,
    content_version: str | None = None,
    started_at: str | None = None,
) -> dict[str, Any]:
    """Wrap the kiosk's report as a KioskIntake v0.2 record.

    The kiosk chooses its own intake_id (a UUID) and the API echoes it back, which is what lets a
    document scanned at stage 7 be addressed to an intake that only gets ingested at stage 9.

    Why every value is an object, not a scalar
    ------------------------------------------
    `fields` is `dict[str, KioskField]`, and a KioskField is required to say `status` - whether
    the question was answered, refused, or asked and left unresolved. A payload of bare scalars
    does not fail loudly: it fails the contract, drops into the backend's LLM repair path, and
    comes back `repaired: true, needs_review: true`, which puts every kiosk intake in front of a
    physician as suspect data. That is what this shape exists to avoid.

    `not_established` therefore belongs here after all, as `unresolved` entries carrying no
    value - the distinction the contract draws, and the one our own report already keeps.

    `hospital_id` is required by the contract. The backend overrides whatever we send with the
    hospital the token is registered to, so naming the wrong one cannot write into another
    hospital's records - but omitting it fails validation before that check is ever reached.
    """

    clinical = report.get("clinical") or {}
    patient = report.get("patient") or {}
    routing = report.get("routing") or {}
    language = patient.get("language")

    fields: dict[str, dict[str, Any]] = {}
    for key in ("complaint", "duration", "severity"):
        if clinical.get(key) is not None:
            fields[FIELD_IDS[key]] = _outcome(clinical[key], language)
    if patient.get("age_years") is not None:
        age = _outcome(patient["age_years"], language)
        age["unit"] = "year"
        fields[FIELD_IDS["age_years"]] = age
    for key, value in (clinical.get("findings") or {}).items():
        fields[FIELD_IDS.get(key, f"screen_{key}")] = _outcome(value, language)
    for key in ("medications", "allergies"):
        # An empty list is an unanswered question, not an answer of "none".
        if clinical.get(key):
            fields[FIELD_IDS[key]] = _outcome(list(clinical[key]), language)
    if patient.get("reported_by"):
        fields["reporter"] = _outcome(patient["reported_by"], language)
    fields.update(_ayurveda_fields(report, language))
    for name in clinical.get("not_established") or []:
        fields.setdefault(FIELD_IDS.get(name, name), {"status": UNRESOLVED})

    turns, source = _turns(report)
    for field_id, turn_id in source.items():
        if field_id in fields:
            fields[field_id]["source_turn"] = turn_id

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "intake_id": intake_id,
        "hospital_id": hospital_id,
        "status": status,
        "language": language or "en",
        "reporter": patient.get("reported_by") or "self",
        "patient_ref": {"type": "guest"},
        "turns": turns,
        "fields": fields,
        "red_flags": [
            {
                "rule_id": flag["rule_id"],
                "severity": flag.get("urgency") or flag.get("severity") or "high",
                "label": flag.get("message") or flag.get("label"),
            }
            for flag in report.get("red_flags") or []
            if flag.get("rule_id")
        ],
    }
    if report.get("generated_at"):
        # The API stamps its own received-at; this is when the interview ended.
        record["completed_at"] = report["generated_at"]
    if started_at:
        record["started_at"] = started_at
    # Which device took this intake, and what was running on it. The hospital's own app sends
    # null for both by design; a kiosk that does the same is indistinguishable from it, and two
    # kiosks in one OPD become impossible to tell apart.
    record["kiosk_id"] = kiosk_id
    record["engine_version"] = engine_version
    if content_version:
        record["content_version"] = content_version
    if routing.get("department_code"):
        record["department_code"] = routing["department_code"]
    return record


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

    # ------------------------------------------------------- what the hospital tells us
    # The only three reads a kiosk token is allowed. Everything else on this API - the
    # worklist, terminology, the intakes themselves - answers 403 for role `kiosk`.

    def consent_notice(self) -> Response:
        """The purposes this hospital asks permission for, labelled in all nine languages."""

        return self._send(urllib.request.Request(f"{self.base_url}/api/v1/content/consent"))

    def hospitals(self) -> Response:
        """Departments, default language and timezone for the hospitals this token can see."""

        return self._send(urllib.request.Request(f"{self.base_url}/api/v1/hospitals"))

    def content_version(self) -> Response:
        """Which question content the hospital is on, recorded with every exported record."""

        return self._send(urllib.request.Request(f"{self.base_url}/api/v1/content/bundle/version"))

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
