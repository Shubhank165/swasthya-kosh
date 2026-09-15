import asyncio
import base64
import contextlib
import copy
import io
import json
import os
import socket
import sqlite3
import time
import uuid
import wave
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from medikiosk import __version__
from medikiosk.clinical.heuristic import HeuristicClinicalExtractor
from medikiosk.clinical.hybrid import HybridClinicalExtractor
from medikiosk.clinical.questions import (
    QUESTIONS,
    TemplateQuestionNaturalizer,
    answer_ui,
)
from medikiosk.clinical.translations import prompt as prompt_text
from medikiosk.config import Settings, get_settings
from medikiosk.edge.runtime import pcm_to_wav, rms
from medikiosk.edge.vad import FRAME_BYTES, SileroVAD, SpeechSegmenter
from medikiosk.kiosk import extraction, handwriting, hospital_sync, slip
from medikiosk.kiosk.abha import VisitRecords
from medikiosk.kiosk.flow import KioskFlow, Stage
from medikiosk.kiosk.protocol import FlowAction, SessionGuard
from medikiosk.kiosk.queue import QueueStore, load_specialties
from medikiosk.kiosk.staff_auth import COOKIE, StaffAuth, StaffSession
from medikiosk.kiosk.voice_actions import (
    Decision,
    match_option,
    parse_command,
    parse_decision,
    review_number,
)
from medikiosk.languages import LANGUAGES
from medikiosk.models import PatientState, RedFlagAlert
from medikiosk.providers.indic_asr import IndicConformerSTT, RoutedSTT
from medikiosk.providers.intake_api import (
    IntakeApi,
    kiosk_envelope,
    load_token,
    redacted,
)
from medikiosk.providers.local_llm_provider import LocalLLMClinicalExtractor
from medikiosk.providers.voices import VoiceBank
from medikiosk.providers.whisper_provider import WhisperCppSTT
from medikiosk.session import ClinicalSession
from medikiosk.storage import EncryptedSessionStore

# sarvamai/openai clients are imported lazily inside the cloud branches below: this device has
# neither package's API key configured, and the local path (Whisper + Piper/Flite, already
# verified on this Jetson) is what actually runs. Importing them eagerly would make every local
# session pay for cloud SDKs it never calls, and sarvamai is not even installed here.

STATIC_DIR = Path(__file__).with_name("static")


def _is_yes(transcript: str) -> bool:
    """Only an unambiguous affirmative confirms the current readback."""
    return parse_decision(transcript) is Decision.YES


# Clinical fields worth attributing on the doctor's sheet. Free-text transcripts are already
# kept verbatim, so only the extracted values need a source recorded against them.
PROVENANCE_FIELDS = (
    "complaint",
    "duration",
    "severity",
    "age_years",
    "fever",
    "vomiting",
    "breathlessness",
    "chest_pain",
    "pain_radiation",
    "sweating",
    "active_bleeding",
    "altered_consciousness",
    "one_sided_weakness",
    "speech_difficulty",
)


class DemoTurnRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=4000)
    language: str = "en-IN"


def _clinical_session(settings: Settings, llm: LocalLLMClinicalExtractor | None) -> ClinicalSession:
    if settings.openai_configured:
        from medikiosk.providers.openai_provider import (
            OpenAIClinicalExtractor,
            OpenAIQuestionNaturalizer,
        )

        extractor: Any = OpenAIClinicalExtractor(
            settings.openai_api_key or "", settings.openai_model
        )
        naturalizer = OpenAIQuestionNaturalizer(
            settings.openai_api_key or "",
            settings.openai_model,
        )
    else:
        # llm is None unless it just passed a health check - a stopped/missing Ollama silently
        # degrades to heuristic-only rather than breaking a demo turn.
        extractor = HybridClinicalExtractor(HeuristicClinicalExtractor(), llm)
        naturalizer = TemplateQuestionNaturalizer()

    if settings.adaptive_questioning:
        # Same surface as ClinicalSession, and it runs this same extractor on every transcript,
        # so red flags are evaluated from the same PatientState as before.
        from medikiosk.clinical.adaptive import AdaptiveClinicalSession, load_agent

        return AdaptiveClinicalSession(
            load_agent(settings.questioning_content_dir),
            extractor,
            settings.edge_language,
        )
    return ClinicalSession(extractor=extractor, naturalizer=naturalizer)


def _wav_pcm_and_rate(wav_bytes: bytes) -> tuple[bytes, int]:
    with wave.open(io.BytesIO(wav_bytes)) as handle:
        return handle.readframes(handle.getnframes()), handle.getframerate()


def emit_log_line(payload: dict[str, Any]) -> None:
    """Write one JSON log line, and never raise.

    Logging must not be able to kill a clinical turn. When stdout cannot encode the text - a
    service started with LANG=C, a Windows console on cp1252 - printing a Hindi transcript raised
    UnicodeEncodeError out of the logger, killed the process_final task, and the patient's answer
    was silently dropped: no next question, and no red flag evaluation of what they just said.
    Fall back to escaped ASCII, then to staying quiet.
    """

    with contextlib.suppress(Exception):  # a broken log stream must not stop the intake
        try:
            print(json.dumps(payload, ensure_ascii=False), flush=True)
        except UnicodeEncodeError:
            print(json.dumps(payload, ensure_ascii=True), flush=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    app = FastAPI(title="MediKiosk Voice", version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    staff_auth = StaffAuth(
        active_settings.staff_users_path, active_settings.staff_allow_insecure_http
    )

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(("/api/", "/dashboard", "/staff")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.post("/api/staff/login")
    async def staff_login(request: Request):
        staff_auth.same_origin(request)
        try:
            raw = bytearray()
            async for chunk in request.stream():
                if len(raw) + len(chunk) > 8192:
                    raise HTTPException(413, "Staff sign-in is too large")
                raw.extend(chunk)
            data = json.loads(raw)
            username, password = data["username"], data["password"]
            if not isinstance(username, str) or not isinstance(password, str):
                raise ValueError
            if not 1 <= len(username) <= 100 or not 1 <= len(password) <= 1024:
                raise ValueError
            # JSON escapes can produce lone surrogates even in a valid UTF-8 body.
            username.encode("utf-8")
            password.encode("utf-8")
        except (ValueError, KeyError, TypeError, RecursionError):
            raise HTTPException(400, "Invalid staff sign-in") from None
        token, staff = await asyncio.to_thread(staff_auth.login, request, username, password)
        response = JSONResponse({"identity": staff.identity, "csrf_token": staff.csrf})
        response.set_cookie(
            COOKIE,
            token,
            max_age=1800,
            httponly=True,
            samesite="strict",
            secure=not active_settings.staff_allow_insecure_http,
            path="/",
        )
        return response

    @app.get("/api/staff/session")
    async def staff_session(staff: Annotated[StaffSession, Depends(staff_auth.require)]):
        return {"identity": staff.identity, "csrf_token": staff.csrf}

    @app.post("/api/staff/logout")
    async def staff_logout(
        request: Request, staff: Annotated[StaffSession, Depends(staff_auth.require)]
    ):
        staff_auth.logout(request)
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, path="/")
        return response

    store = None
    records = None
    if active_settings.session_encryption_key:
        store = EncryptedSessionStore(
            active_settings.session_store_path,
            active_settings.session_encryption_key,
        )
        # Past-visit lookup for a returning ABHA holder. Same key, separate file: the session
        # store is keyed by session id and this one by a hash of the ABHA number.
        records = VisitRecords(
            active_settings.session_store_path.with_name("visits.db"),
            active_settings.session_encryption_key,
        )

    # Resident local speech providers, shared across every browser session that connects. Piper
    # keeps its process alive between calls (a fresh process per prompt cost ~2s on this board),
    # and constructing WhisperCppSTT is free - it only holds a base URL.
    whisper = WhisperCppSTT(active_settings.whisper_url)
    stt = RoutedSTT(whisper, IndicConformerSTT(active_settings.indic_asr_url))
    voices = VoiceBank(
        active_settings.piper_binary,
        active_settings.voice_dir,
        active_settings.flite_binary,
        active_settings.flite_voice_dir,
        active_settings.prerendered_audio_dir,
    )
    ocr_model: dict[str, Any] = {"instance": None}
    # The hospital's cloud, if this kiosk has been provisioned for one. Three things must be
    # true before a record leaves the building, checked in this order: the device is configured
    # for it, a token exists, and - at the end of each encounter - the patient granted
    # `cloud_intake` for that purpose. Neither of the first two is permission; they only decide
    # whether asking is possible at all.
    cloud: dict[str, Any] = {"api": None, "hospital_id": None, "config": {}}
    cloud_cache = active_settings.session_store_path.parent / "hospital"
    if active_settings.handwritten_cloud_ocr:
        kiosk_token = load_token(active_settings.intake_token_path)
        if not kiosk_token:
            emit_log_line({"event": "cloud_unprovisioned", "reason": "no_kiosk_token"})
        else:
            api = IntakeApi(kiosk_token, active_settings.intake_api_url)
            # whoami is the only authority on which hospital this token writes into: the
            # backend overrides whatever a payload claims, so asking is not optional.
            identity = api.whoami()
            if identity.ok and (identity.body or {}).get("hospital_id"):
                cloud = {
                    "api": api,
                    "hospital_id": identity.body["hospital_id"],
                    # Offline-first: the refresh may fail, and every later read of the
                    # hospital's purposes and departments comes off this cache.
                    "config": hospital_sync.refresh(api, cloud_cache),
                }
                emit_log_line(
                    {
                        "event": "cloud_ready",
                        "hospital": cloud["hospital_id"],
                        "token": redacted(kiosk_token),
                        "consent_version": hospital_sync.consent_version(cloud["config"]),
                        "content_version": hospital_sync.content_version(cloud["config"]),
                    }
                )
            else:
                # No internet at startup is normal. Run on whatever was cached last time.
                cloud = {
                    "api": api,
                    "hospital_id": None,
                    "config": hospital_sync.load(cloud_cache),
                }
                emit_log_line(
                    {"event": "cloud_unreachable", "detail": identity.detail[:120] or "no identity"}
                )
    ocr_lock = asyncio.Lock()
    # The receiving half of the product: a report nobody can read is not a finished intake.
    queue = QueueStore(
        active_settings.session_store_path.with_name("queue.db"),
        encryption_key=active_settings.session_encryption_key,
    )

    def reconcile_queue() -> None:
        if store is None:
            return
        for entry in queue.finalizing():
            receipt = store.load_report(entry.encounter_id)
            if (receipt or {}).get("completion") == "saved_local":
                queue.publish(entry.encounter_id)

    # The report and workflow share a transaction; queue publication is recoverable,
    # not a claimed transaction across two database files.
    reconcile_queue()
    specialties = load_specialties(active_settings.session_store_path.with_name("specialties.json"))
    # Reports live in memory for the doctor view. They are already persisted encrypted in the
    # session store; this is a read cache so the dashboard does not decrypt on every poll.
    reports: dict[str, dict[str, Any]] = {}

    def load_report(encounter_id: str) -> dict | None:
        report = reports.get(encounter_id)
        if report is None and store is not None:
            report = store.load_report(encounter_id)
            if report is not None:
                reports[encounter_id] = report
        return report

    # Unfinished intakes, kept so a dropped connection can continue rather than restart.
    resume_states: dict[str, dict[str, Any]] = {}
    active_sessions: dict[str, dict[str, Any]] = {}
    leased_tokens: set[str] = set()

    def scan_owner(
        request: Request, purpose: str, stage: Stage | frozenset[Stage]
    ) -> dict[str, Any]:
        owned = active_sessions.get(request.headers.get("X-Kiosk-Session", ""))
        if owned is None or not owned["guard"].owns(
            request.headers.get("X-Kiosk-Session", ""),
            request.headers.get("X-Kiosk-Token", ""),
        ):
            raise HTTPException(401, "An active kiosk session is required")
        stages = stage if isinstance(stage, frozenset) else frozenset({stage})
        if (
            owned["flow"].stage not in stages
            or not owned["flow"].consent.allows(purpose)
            or request.headers.get("X-Kiosk-Revision") != str(owned["guard"].revision)
        ):
            raise HTTPException(409, "Scan is not authorized for the current prompt")
        return owned

    # The kiosk screen, when one is attached. Shared across sessions because there is one physical
    # display: a tablet in front of the kiosk shows whatever the current patient is being asked.
    # Best-effort exactly like PanelView - a display fault never interrupts an interview.
    tablet: Any = None
    if active_settings.panel_enabled and active_settings.panel_target == "tablet":
        try:
            from medikiosk.edge.tablet import TabletPanel

            tablet = TabletPanel(port=active_settings.panel_port, scale=active_settings.panel_scale)
            tablet.open()
            # Show something immediately. The MJPEG stream has nothing to send until a screen is
            # rendered, so without this the display just spins on a blank tab until a patient
            # happens to connect - and a kiosk screen that looks broken when idle is broken.
            from medikiosk.edge.display import Screen, render
            from medikiosk.kiosk.flow import text as flow_text

            tablet.show(
                render(
                    Screen(
                        language=active_settings.edge_language[:2],
                        headline=flow_text("idle", active_settings.edge_language),
                    ),
                    active_settings.panel_scale,
                )
            )
        except OSError as error:
            # Usually the port is already held by a stale display process. A kiosk that refuses to
            # start because a screen is busy is worse than one that runs without the screen.
            print(
                f"kiosk display unavailable on :{active_settings.panel_port}: {error}", flush=True
            )
            tablet = None

    llm_extractor = (
        LocalLLMClinicalExtractor(active_settings.clinical_llm_model, active_settings.ollama_url)
        if active_settings.clinical_llm_enabled
        else None
    )

    def local_speech_ready() -> bool:
        return stt.health()

    def clinical_session() -> ClinicalSession:
        llm = llm_extractor if llm_extractor and llm_extractor.health() else None
        # Patient input must not reach a configured external extractor by accident.
        local_settings = active_settings.model_copy(update={"openai_api_key": None})
        return _clinical_session(local_settings, llm)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "profile": active_settings.deployment_profile,
            "openai": {
                "configured": active_settings.openai_configured,
                "model": active_settings.openai_model,
            },
            "sarvam": {
                "configured": active_settings.sarvam_configured,
                "stt_model": "saaras:v3-realtime",
                "tts_model": "bulbul:v3",
            },
            "local_voice": {
                "whisper_reachable": await asyncio.to_thread(whisper.health),
                "indic_asr_reachable": await asyncio.to_thread(stt.indic.health),
                "languages": sorted(LANGUAGES),
            },
            "storage": {"encrypted": store is not None},
        }

    @app.post("/api/demo-turn")
    async def demo_turn(request: DemoTurnRequest) -> dict[str, Any]:
        if active_settings.deployment_profile != "demo":
            raise HTTPException(404, "Not found")
        session = await asyncio.to_thread(clinical_session)
        result = await session.process_transcript(request.transcript, request.language)
        return result.model_dump(mode="json")

    @app.post("/api/ocr")
    async def ocr(request: Request, image: UploadFile) -> dict[str, Any]:
        """Read a document only for the active, consenting encounter."""
        owner = scan_owner(request, "local_documents", Stage.DOCUMENTS)
        revision = owner["guard"].revision
        from PIL import Image

        payload = await image.read(12 * 1024 * 1024 + 1)
        if len(payload) > 12 * 1024 * 1024:
            raise HTTPException(413, "Image exceeds 12 MB")
        try:
            with Image.open(io.BytesIO(payload)) as uploaded:
                uploaded.verify()
        except (OSError, ValueError) as exc:
            raise HTTPException(422, "Upload a readable image") from exc

        async with ocr_lock:
            if ocr_model["instance"] is None:
                try:
                    from ocr.models.adapters import PPOcrOnnx

                    model = PPOcrOnnx(str(Path("offline/jetson/models/ppocr_onnx")))
                    await asyncio.to_thread(model.load)
                    ocr_model["instance"] = model
                except Exception as exc:
                    raise HTTPException(503, "OCR model is unavailable on this kiosk") from exc
            workdir = active_settings.session_store_path.parent / "ocr_uploads"
            workdir.mkdir(mode=0o700, parents=True, exist_ok=True)
            # The OCR adapter requires a pathname. Keep this short-lived local
            # image private; never add it to a transfer queue implicitly.
            photo = workdir / f"{uuid.uuid4().hex}.jpg"
            try:
                with os.fdopen(
                    os.open(photo, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
                ) as handle:
                    handle.write(payload)
                started = time.monotonic()
                text, scores = await asyncio.to_thread(ocr_model["instance"].read, photo)
                elapsed = time.monotonic() - started
            except Exception as exc:
                raise HTTPException(503, "Document recognition failed; please retry") from exc
            finally:
                photo.unlink(missing_ok=True)

        lines = [line for line in text.splitlines() if line.strip()]
        # Structure it here so every client gets the same parse, and so the doctor sees
        # medications and lab values rather than a wall of OCR text.
        structured = extraction.extract(lines)

        # Printed or handwritten? The recognizer is trained on printed Devanagari, so its
        # per-line confidence collapses on handwriting. A page judged handwritten is held for the
        # cloud reader - but only when that path is on and a token exists; otherwise the local
        # read is all there is, and it is returned flagged so nobody mistakes it for a good one.
        verdict = handwriting.assess(scores)
        outbox_handle: str | None = None
        # Local OCR permission does not authorize retaining or sending an image.
        # The cloud path remains blocked pending the hospital's consent mapping.
        if (
            owner is not active_sessions.get(owner["guard"].session_id)
            or revision != owner["guard"].revision
            or not owner["flow"].consent.allows("local_documents")
        ):
            raise HTTPException(409, "The session changed during scanning")

        emit_log_line(
            {
                "event": "ocr_read",
                "lines": len(lines),
                "parsed": structured["parsed_count"],
                "seconds": round(elapsed, 2),
                "handwritten": verdict.handwritten,
                "low_line_share": round(verdict.low_line_share, 2),
                "held_for_cloud": outbox_handle is not None,
            }
        )
        result = {
            "capture_id": uuid.uuid4().hex,
            "lines": lines,
            "text": "\n".join(lines),
            "seconds": round(elapsed, 2),
            "handwritten": verdict.handwritten,
            "confidence_note": verdict.reason,
            "outbox_handle": outbox_handle,
        }
        captures = owner["captures"]
        # Retakes replace ephemeral previews, not patient-owned documents.
        while len(captures) >= 8:
            captures.pop(next(iter(captures)))
        captures[result["capture_id"]] = result
        return result

    @app.get("/api/slip.pdf")
    async def slip_pdf(request: Request) -> Response:
        """The finished slip, for the tablet to hand to the patient as a file.

        Same ownership rule as a document scan: the capability that owns this encounter, on
        the current prompt, and only once there is a saved report to print.
        """

        owner = scan_owner(request, "local_intake", frozenset({Stage.REPORT, Stage.EMERGENCY}))
        report = owner["flow"].report or {}
        if report.get("completion") != "saved_local":
            raise HTTPException(409, "The slip is not ready yet")
        pdf = await asyncio.to_thread(
            slip.render,
            report,
            owner["flow"].language or "en",
            {
                "deva": active_settings.slip_font_devanagari,
                "latin": active_settings.slip_font_latin,
            },
        )
        short = str(report.get("encounter_id") or "")[:8]
        return Response(
            pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="medikiosk-slip-{short}.pdf"',
                "Cache-Control": "no-store",
            },
        )

    @app.post("/api/abha-scan")
    async def abha_scan(request: Request, image: UploadFile) -> dict[str, Any]:
        """Decode an ABHA QR from a photographed card.

        The decoding happens here rather than in the tablet app so the app needs no zbar build:
        OpenCV's detector is already installed on this device and proven against the same cards.
        """

        from PIL import Image

        from medikiosk.kiosk.abha import scan_qr

        owner = scan_owner(request, "local_intake", Stage.ABHA)
        revision = owner["guard"].revision
        payload = await image.read(12 * 1024 * 1024 + 1)
        if len(payload) > 12 * 1024 * 1024:
            raise HTTPException(413, "Image exceeds 12 MB")
        try:
            photo = Image.open(io.BytesIO(payload)).convert("RGB")
        except (OSError, ValueError) as exc:
            raise HTTPException(422, "Upload a readable image") from exc
        number = await asyncio.to_thread(scan_qr, photo)
        current = scan_owner(request, "local_intake", Stage.ABHA)
        if current is not owner or revision != owner["guard"].revision:
            raise HTTPException(409, "The session changed during scanning")
        print(
            json.dumps({"event": "abha_scan", "found": bool(number)}, ensure_ascii=False),
            flush=True,
        )
        # The tablet submits the decoded number to its own intake; reports use only last4.
        return {"found": bool(number), "number": number, "last4": number[-4:] if number else None}

    @app.get("/dashboard")
    async def dashboard_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "dashboard.html")

    @app.get("/api/queue")
    async def api_queue(
        staff: Annotated[StaffSession, Depends(staff_auth.require)],
    ) -> dict[str, Any]:
        """The OPD list. Review cases first - they are not merely high priority."""

        reconcile_queue()
        entries = queue.waiting()
        return {
            "specialties": specialties,
            "review": [vars(e) for e in entries if e.needs_review],
            "waiting": [vars(e) for e in entries if not e.needs_review],
        }

    @app.get("/api/encounters/{encounter_id}")
    async def api_encounter(
        encounter_id: str, staff: Annotated[StaffSession, Depends(staff_auth.require)]
    ) -> dict[str, Any]:
        report = load_report(encounter_id)
        if report is None:
            return {"error": "unknown encounter"}
        entry = queue.get(encounter_id)
        return {
            "encounter_id": encounter_id,
            "queue": vars(entry) if entry else None,
            "report": report,
        }

    @app.post("/api/encounters/{encounter_id}/state")
    async def api_set_state(
        encounter_id: str, body: dict, staff: Annotated[StaffSession, Depends(staff_auth.require)]
    ) -> dict[str, Any]:
        """Doctor lifecycle: WAITING to IN_CONSULTATION to COMPLETED."""

        state = str(body.get("state", "")).upper()
        if state not in ("WAITING", "IN_CONSULTATION", "COMPLETED"):
            return {"error": f"unknown state {state!r}"}
        entry = queue.get(encounter_id)
        if entry is None or entry.state == "FINALIZING":
            raise HTTPException(409, "Encounter is not ready for consultation")
        queue.set_state(encounter_id, state)
        print(
            json.dumps({"event": "queue_state", "encounter": encounter_id[:8], "state": state}),
            flush=True,
        )
        return {"ok": True, "state": state}

    @app.post("/api/encounters/{encounter_id}/correct")
    async def api_correct(
        encounter_id: str, body: dict, staff: Annotated[StaffSession, Depends(staff_auth.require)]
    ) -> dict[str, Any]:
        """A clinician fixing a value. Supersedes rather than overwrites, so the original stays."""

        report = load_report(encounter_id)
        if report is None:
            return {"error": "unknown encounter"}
        key, value = str(body.get("key", "")), body.get("value")
        report = copy.deepcopy(report)
        by = staff.identity
        if not key:
            return {"error": "key required"}
        entries = report.setdefault("provenance", {}).setdefault("entries", [])
        entries.append(
            {
                "key": key,
                "value": value,
                "source": "DOCTOR_VERIFIED",
                "confidence": None,
                "evidence": body.get("evidence"),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "superseded_by": None,
                "corrected_by": by,
            }
        )
        for entry in entries[:-1]:
            if entry.get("key") == key and entry.get("superseded_by") is None:
                entry["superseded_by"] = by
        if store is None:
            raise HTTPException(503, "Encrypted storage unavailable")
        store.save_report(encounter_id, report)
        reports[encounter_id] = report
        print(
            json.dumps({"event": "correction", "encounter": encounter_id[:8], "key": key}),
            flush=True,
        )
        return {"ok": True}

    @app.websocket("/ws/session")
    async def voice_session(websocket: WebSocket) -> None:
        protocols = websocket.scope.get("subprotocols", [])
        await websocket.accept(subprotocol="medikiosk.v2" if "medikiosk.v2" in protocols else None)
        # Capabilities must not appear in request URLs/access logs. Never resume
        # from a public encounter ID or an old client's query parameter.
        if websocket.scope.get("query_string"):
            await websocket.close(code=4400, reason="Use protocol 2 resume capability")
            return
        resumed = next((p[7:] for p in protocols if p.startswith("resume.")), None)
        restored = None
        if resumed:
            if resumed in leased_tokens:
                await websocket.close(code=4409, reason="Session already active")
                return
            restored = resume_states.pop(resumed, None)
            if restored is None and store is not None:
                loaded = store.load_workflow(resumed)
                if loaded:
                    restored = loaded["data"]
            if restored is None:
                await websocket.close(code=4404, reason="Session cannot be resumed")
                return
        guard = SessionGuard(
            restored["guard"]["session_id"] if restored else None,
            resumed if restored else None,
        )
        session_id = guard.session_id
        leased_tokens.add(guard.token)
        try:
            session = await asyncio.to_thread(clinical_session)
        except BaseException:
            leased_tokens.discard(guard.token)
            raise
        audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=80)
        send_lock = asyncio.Lock()
        turn_tasks: set[asyncio.Task[Any]] = set()
        stt_task: asyncio.Task[Any] | None = None
        tts_task: asyncio.Task[Any] | None = None
        idle_task: asyncio.Task[Any] | None = None
        # The question this session just asked, so a bare "three days" or "haan" binds to that
        # field instead of forcing every extractor to parse duration/yes-no out of raw text. This
        # is the same asked= mechanism edge.runtime uses for the wired kiosk; the web path never
        # had it, which is why it kept re-asking "how long have you had this problem?" - a plain
        # "three days" answer had nowhere to attach without knowing which question it answered.
        pending_question = None
        intake_complete = False
        # How many times each question has been asked, and the ones we gave up on. The wired
        # kiosk has always done this; the web path did not, so a patient who could not answer
        # ask_age was asked it forever with no way forward.
        attempts: dict[str, int] = {}
        unresolved: list[str] = []
        # The eight-step workflow around the clinical interview. It owns no clinical logic - the
        # state machine, red flags and extractors are unchanged - it only decides which stage the
        # patient is on and what the client should render.
        flow = KioskFlow()
        # Red flags accumulate across the whole session: one fired during the interview still has
        # to appear on the report built several stages later.
        session_red_flags: list[Any] = []

        def log(event: str, **fields: Any) -> None:
            # One JSON line per event on stdout, next to uvicorn's own request log. Without this
            # the only way to see what a session actually said was decrypting the SQLite store by
            # hand after the fact - useless for debugging live.
            #
            # Logging must never be able to kill a clinical turn. When stdout cannot encode the
            # text - a service started with LANG=C, a Windows console on cp1252 - printing a Hindi
            # transcript raised UnicodeEncodeError out of here, killed the process_final task, and
            # the patient's answer was silently dropped: no next question, and no red flag
            # evaluation for what they just said. Fall back to escaped ASCII, then to nothing.
            # Ordinary diagnostics contain identifiers/counters, never patient words.
            safe = {
                key: value
                for key, value in fields.items()
                if key not in {"text", "heard", "transcript", "final_state", "message", "detail"}
            }
            emit_log_line({"session": session_id[:8], "event": event, **safe})

        # Cloud (Sarvam) takes priority if it is genuinely configured; this device has no Sarvam
        # key, so every session on this Jetson runs the local branch - the same Whisper + Piper
        # stack proven in medikiosk.edge.runtime, driven by network audio instead of a local mic.
        use_cloud = False  # No external ASR/TTS in the offline patient journey.
        use_local = await asyncio.to_thread(local_speech_ready)
        local_language = active_settings.edge_language
        local_language_locked = not active_settings.auto_detect_language
        local_vad = None
        if use_local:
            try:
                local_vad = await asyncio.to_thread(SileroVAD, active_settings.silero_model_path)
            except Exception as exc:
                use_local = False
                log("vad_unavailable", message=str(exc))
        local_segmenter = SpeechSegmenter(
            threshold=active_settings.vad_threshold,
            start_ms=active_settings.vad_start_ms,
            silence_ms=active_settings.vad_silence_ms,
            max_utterance_s=active_settings.max_utterance_s,
        )

        transition_active = False
        pending_events: list[dict[str, Any]] = []

        async def send(payload: dict[str, Any]) -> None:
            payload = {"session_id": session_id, "revision": guard.revision, **payload}
            if transition_active and payload["type"] not in {"clinical.processing", "staff.alert"}:
                pending_events.append(payload)
                return
            async with send_lock:
                await websocket.send_json(payload)

        async def cancel_tts(reason: str) -> None:
            nonlocal tts_task
            if tts_task and not tts_task.done():
                tts_task.cancel()
                with suppress(asyncio.CancelledError):
                    await tts_task
                tts_task = None
            await send({"type": "tts.cancelled", "reason": reason})

        async def stream_tts(text: str, language: str | None, epoch: tuple[str, int]) -> None:
            if not use_local or epoch != (session_id, guard.revision):
                return
            lang = (language or local_language)[:2]
            if lang not in LANGUAGES or not voices.available(lang):
                await send(
                    {
                        "type": "error",
                        "stage": "tts",
                        "message": "Selected offline voice is unavailable",
                    }
                )
                return
            await send({"type": "tts.start", "sample_rate": 0, "playback_rate": playback_rate})
            try:
                wav_bytes = await asyncio.to_thread(voices.synthesize, text, lang)
                if epoch != (session_id, guard.revision):
                    return
                pcm, rate = _wav_pcm_and_rate(wav_bytes)
                await send(
                    {
                        "type": "tts.audio",
                        "encoding": "linear16",
                        "sample_rate": rate,
                        "audio": base64.b64encode(pcm).decode("ascii"),
                    }
                )
                await send({"type": "tts.end"})
            except asyncio.CancelledError:
                raise
            except Exception:
                await send(
                    {"type": "error", "stage": "tts", "message": "Offline speech is unavailable"}
                )

        turn_lock = asyncio.Lock()
        audio_generation = 0
        capture_epoch: tuple[str, int] | None = None
        playback_active = False
        playback_rate = 1.0
        last_activity = time.monotonic()
        idle_seconds = active_settings.idle_timeout_s
        pending_speech: tuple[str, str | None, tuple[str, int]] | None = None

        def snapshot() -> dict[str, Any]:
            return {
                "flow": flow.snapshot(),
                "state": session.state.model_dump(mode="json"),
                "guard": guard.snapshot(),
                "attempts": attempts,
                "unresolved": unresolved,
                "red_flags": [a.model_dump(mode="json") for a in session_red_flags],
                "pending_question_id": pending_question.id if pending_question else None,
                "status": "complete" if intake_complete else "active",
            }

        def persist() -> None:
            if transition_active:
                return
            data = snapshot()
            if store is not None:
                existing = store.load_report(session_id) if intake_complete else None
                if intake_complete and (existing or {}).get("completion") != "saved_local":
                    store.save_completion(session_id, data, guard.token)
                else:
                    # A receipt resume never overwrites subsequent staff corrections.
                    store.save_workflow(session_id, data, guard.token)
            elif flow.consent.allows("local_intake"):
                raise RuntimeError("Encrypted storage is required for patient intake")
            resume_states[guard.token] = data

        @contextlib.asynccontextmanager
        async def transition(
            action: FlowAction | None = None, epoch: tuple[str, int] | None = None
        ):
            """Save state and the action receipt together, before exposing the next prompt."""
            nonlocal transition_active, flow, guard, session, session_id, pending_question
            nonlocal intake_complete, pending_speech, last_activity
            nonlocal local_language, local_language_locked
            nonlocal playback_active, playback_rate, idle_seconds
            async with turn_lock:
                if epoch is not None and epoch != (session_id, guard.revision):
                    raise ValueError("The prompt changed")
                if action is not None:
                    if not guard.check(action):
                        raise ValueError("Action was already accepted")
                    if action.action in {
                        "answer",
                        "choose",
                        "confirm",
                        "unknown",
                        "refuse",
                        "skip",
                    }:
                        expected_question = flow.screen(session.state).get("question_id")
                        if (
                            flow.stage is Stage.INTERVIEW
                            and not flow.restart_confirm
                            and not flow.withdraw_confirm
                        ):
                            if pending_question is None:
                                raise ValueError("No clinical question is active")
                            expected_question = pending_question.id
                        if action.question_id != expected_question:
                            raise ValueError("Question changed or missing")
                old_flow, old_guard = copy.deepcopy(flow), copy.deepcopy(guard)
                old_session = session
                old_snapshot = copy.deepcopy(snapshot())
                old_language = local_language, local_language_locked
                old_playback = playback_active, playback_rate, idle_seconds
                old_state = session.state.model_copy(deep=True)
                old_question = pending_question
                old_attempts, old_unresolved = attempts.copy(), unresolved.copy()
                old_flags, old_complete = session_red_flags.copy(), intake_complete
                old_captures = copy.deepcopy(active_sessions[session_id]["captures"])
                pending_events.clear()
                pending_speech = None
                transition_active = True
                try:
                    yield
                    if action is not None and action.session_id == guard.session_id:
                        guard.accept(action)
                    transition_active = False
                    if guard.session_id != old_guard.session_id:
                        retired_guard = copy.deepcopy(old_guard)
                        if action is not None:
                            retired_guard.accept(action)
                        old_snapshot["guard"] = retired_guard.snapshot()
                        old_snapshot["status"] = "closed"
                        fresh = snapshot()
                        if store is not None:
                            store.restart_workflow(
                                old_snapshot, old_guard.token, fresh, guard.token
                            )
                        elif old_flow.consent.allows("local_intake"):
                            raise RuntimeError("Encrypted storage is required for patient intake")
                        resume_states.pop(old_guard.token, None)
                        resume_states[guard.token] = fresh
                        leased_tokens.discard(old_guard.token)
                    else:
                        persist()
                except BaseException:
                    transition_active = False
                    pending_events.clear()
                    pending_speech = None
                    leased_tokens.discard(guard.token)
                    active_sessions.pop(session_id, None)
                    flow, guard, session_id = old_flow, old_guard, old_guard.session_id
                    session = old_session
                    session.state = old_state
                    local_language, local_language_locked = old_language
                    playback_active, playback_rate, idle_seconds = old_playback
                    if hasattr(session, "language"):
                        session.language = local_language
                    pending_question = old_question
                    attempts.clear()
                    attempts.update(old_attempts)
                    unresolved[:] = old_unresolved
                    session_red_flags[:] = old_flags
                    intake_complete = old_complete
                    active_sessions[session_id] = {
                        "flow": flow,
                        "guard": guard,
                        "captures": old_captures,
                    }
                    leased_tokens.add(guard.token)
                    invalidate_audio()
                    raise
                events, speech = pending_events.copy(), pending_speech
                pending_events.clear()
                pending_speech = None
                last_activity = time.monotonic()
                if intake_complete:
                    reports[session_id] = store.load_report(session_id) if store else flow.report
                    try:
                        queue.publish(session_id)
                    except (OSError, sqlite3.Error):
                        log("queue_publication_pending")
                for event in events:
                    await send(event)
                if speech is not None:
                    queue_speech(*speech)

        def invalidate_audio() -> None:
            nonlocal audio_generation, capture_epoch
            audio_generation += 1
            capture_epoch = None
            local_segmenter.reset()
            if local_vad is not None:
                local_vad.reset()
            while not audio_queue.empty():
                audio_queue.get_nowait()

        async def handle_action(
            action: str, value: Any = None, question_id: str | None = None, method: str = "touch"
        ) -> None:
            nonlocal pending_question, local_language, local_language_locked
            nonlocal flow, session, session_id, guard, intake_complete, playback_active
            nonlocal playback_rate, last_activity, idle_seconds
            if (
                flow.edit_target is not None
                and flow.edit_return
                and action in {"cancel", "back"}
                and not flow.restart_confirm
                and not flow.withdraw_confirm
            ):
                session.state = PatientState.model_validate(flow.edit_return["state"])
                attempts.clear()
                attempts.update(flow.edit_return.get("attempts", {}))
                unresolved[:] = flow.edit_return.get("unresolved", [])
                flow.edit_target = None
                flow.edit_return = None
                flow.stage = Stage.REVIEW
                pending_question = None
                await send_screen()
                return
            if (
                flow.restart_confirm or flow.withdraw_confirm or flow.edit_target is not None
            ) and action in {"cancel", "back"}:
                flow.action(action, value, question_id, method=method)
                await send_screen()
                return
            if action in {"repeat", "slower", "more_time", "cancel"}:
                if action == "slower":
                    playback_rate = 0.8
                elif action == "more_time":
                    idle_seconds = active_settings.idle_timeout_s * 2
                last_activity = time.monotonic()
                await send_screen()
                return
            if action in {"unknown", "refuse", "skip"} and flow.stage is Stage.INTERVIEW:
                if pending_question is None:
                    return
                status = "refused" if action == "refuse" else "unresolved"
                flow.record_answer(
                    pending_question.id,
                    pending_question.template_for(flow.language),
                    "",
                    status=status,
                    field=pending_question.target_field,
                    method=method,
                )
                if pending_question.id not in unresolved:
                    unresolved.append(pending_question.id)
                if flow.edit_target is not None:
                    for entry in flow.ledger.entries:
                        if (
                            entry.key == pending_question.target_field
                            and entry.superseded_by is None
                        ):
                            entry.superseded_by = f"answer:{len(flow.answers)}"
                    flow.edit_target = None
                    flow.edit_return = None
                    flow.stage = Stage.REVIEW
                pending_question = None
                await send_screen()
                return
            if action in {"keep", "discard", "retake"} and flow.stage is Stage.DOCUMENTS:
                preview = flow.document_preview
                if action == "keep":
                    if preview is None:
                        raise ValueError("No preview to keep")
                    flow.add_document(
                        preview["lines"],
                        preview.get("seconds"),
                        handwritten=preview.get("handwritten"),
                    )
                    flow.documents[-1].update(
                        {
                            key: preview.get(key)
                            for key in ("capture_id", "confidence_note", "outbox_handle")
                        }
                    )
                flow.document_preview = None
                await send_screen()
                if action == "retake":
                    await send({"type": "device.action", "action": "scan"})
                return
            if action in {"document", "preview"}:
                owned = active_sessions[session_id]
                capture_id = value.get("capture_id") if isinstance(value, dict) else None
                result = owned["captures"].get(capture_id)
                if flow.document_preview is not None:
                    raise ValueError("Resolve the current preview first")
                if (
                    result is None
                    or flow.stage is not Stage.DOCUMENTS
                    or not flow.consent.allows("local_documents")
                ):
                    raise ValueError("Unowned document capture")
                flow.document_preview = copy.deepcopy(result)
                owned["captures"].pop(capture_id)
                await send_screen()
                return
            prior_answers = len(flow.answers)
            effect = flow.action(action, value, question_id, method=method)
            if len(flow.answers) > prior_answers and flow.answers[-1]["id"] == "registration.age":
                accepted = flow.answers[-1]
                age = accepted["value"] if accepted["status"] == "answered" else None
                session.state.age_years = age
                for entry in flow.ledger.entries:
                    if entry.key == "age_years" and entry.superseded_by is None:
                        entry.superseded_by = f"answer:{accepted['turn']}"
                for previous in flow.answers[:-1]:
                    if previous["id"] == "ask_age":
                        previous["superseded"] = True
                if age is not None:
                    flow.ledger.record(
                        "age_years", age, flow.spoken_source, evidence=accepted["answer"]
                    )
            if effect == "restart":
                replacement = await asyncio.to_thread(clinical_session)
                active_sessions.pop(session_id, None)
                guard = SessionGuard()
                session_id = guard.session_id
                leased_tokens.add(guard.token)
                flow = KioskFlow()
                session = replacement
                session_red_flags.clear()
                attempts.clear()
                unresolved.clear()
                intake_complete = False
                pending_question = None
                playback_active = False
                playback_rate = 1.0
                idle_seconds = active_settings.idle_timeout_s
                active_sessions[session_id] = {"flow": flow, "guard": guard, "captures": {}}
                local_language = active_settings.edge_language
                local_language_locked = False
                await send({"type": "session.id", "session_token": guard.token})
            elif effect == "finalize":
                # Provisioned for a hospital, and the patient has not yet been asked whether
                # this record may be sent there. Ask now, on the record they just reviewed;
                # answering it comes back here as another "finalize".
                if (
                    cloud["api"] is not None
                    and cloud["hospital_id"] is not None
                    and not flow.transfer_decided
                ):
                    flow.ask_transfer_permission()
                    await send_screen()
                    return
                await finish_session()
                return
            elif effect in {"scan", "retake", "discard"}:
                await send({"type": "device.action", "action": effect})
                return
            elif effect == "help":
                await send({"type": "staff.alert", "status": "requested", "acknowledged": False})
            elif effect == "edit":
                target = flow.edit_target
                question = QUESTIONS.get(target or "")
                if question is None:
                    raise ValueError("This answer requires staff correction")
                flow.edit_return = {
                    "state": session.state.model_dump(mode="json"),
                    "attempts": attempts.copy(),
                    "unresolved": unresolved.copy(),
                }
                previous_value = getattr(session.state, question.target_field)
                setattr(
                    session.state,
                    question.target_field,
                    [] if isinstance(previous_value, list) else None,
                )
                unresolved[:] = [q for q in unresolved if q != question.id]
                attempts.pop(question.id, None)
                pending_question = question
                flow.stage = Stage.INTERVIEW
            local_language = flow.language or local_language
            local_language_locked = bool(flow.language)
            if hasattr(session, "language"):
                session.language = local_language
            await send_screen()

        async def process_final(
            transcript: str,
            language: str | None,
            spoken: bool = True,
            action: FlowAction | None = None,
            epoch: tuple[str, int] | None = None,
        ) -> None:
            async with transition(action=action, epoch=epoch):
                nonlocal tts_task, pending_question, intake_complete
                if flow.stage is Stage.REVIEW and (number := review_number(transcript)) is not None:
                    live = [a for a in flow.answers if not a.get("superseded")]
                    if not 1 <= number <= len(live):
                        raise ValueError("Choose a current review answer")
                    await handle_action(
                        "edit", live[number - 1]["id"], method="voice" if spoken else "touch"
                    )
                    return
                command_name = parse_command(transcript, flow.language)
                if command_name:
                    await handle_action(command_name, method="voice" if spoken else "touch")
                    return
                if (
                    flow.stage is not Stage.INTERVIEW
                    or flow.restart_confirm
                    or flow.withdraw_confirm
                ):
                    screen = flow.screen(session.state)
                    choice = match_option(transcript, screen.get("options", []), flow.language)
                    if choice is not None:
                        await handle_action(
                            "choose",
                            choice,
                            screen.get("question_id"),
                            method="voice" if spoken else "touch",
                        )
                    elif screen.get("input") in {"text", "camera_or_text", "number"}:
                        await handle_action(
                            "answer",
                            transcript,
                            screen.get("question_id"),
                            method="voice" if spoken else "touch",
                        )
                    else:
                        await send_screen()
                    return
                if not flow.consent.allows("local_intake"):
                    await send(
                        {
                            "type": "error",
                            "stage": "consent",
                            "message": "Intake permission required",
                        }
                    )
                    return
                if intake_complete:
                    # Do not transcribe post-completion conversation into a closed record.
                    log("ignored_after_close", text=transcript)
                    return
                answer_method = "voice" if spoken else "touch"

                asked = pending_question
                log(
                    "transcript",
                    text=transcript,
                    language=language,
                    asked=asked.id if asked else None,
                )
                await send({"type": "clinical.processing"})
                try:
                    result = await session.process_transcript(
                        transcript, flow.language or language, asked=asked, skip=unresolved
                    )
                    if result.next_question_id:
                        question_id = result.next_question_id
                        attempts[question_id] = attempts.get(question_id, 0) + 1
                        if attempts[question_id] > active_settings.max_question_attempts:
                            unresolved.append(question_id)
                            question = session.state_machine.next_question(
                                session.state, unresolved
                            )
                            result.next_question_id = question.id if question else None
                            result.next_question = (
                                question.template_for(flow.language) if question else None
                            )
                            if question:
                                attempts[question.id] = attempts.get(question.id, 0) + 1
                    if asked is not None:
                        value = getattr(result.state, asked.target_field, None)
                        flow.record_answer(
                            asked.id,
                            asked.template_for(flow.language),
                            transcript,
                            status="answered" if value is not None else "unresolved",
                            field=asked.target_field,
                            value=value,
                            method=answer_method,
                        )
                    persist()
                    await send({"type": "clinical.turn", "data": result.model_dump(mode="json")})
                    # Attribute second-hand answers to the representative, not the patient.
                    for field in PROVENANCE_FIELDS:
                        value = getattr(result.state, field, None)
                        prior = flow.ledger.current(field)
                        if value is not None and (prior is None or prior.value != value):
                            for entry in flow.ledger.entries:
                                if (
                                    entry.key == field
                                    and entry.source == flow.spoken_source
                                    and entry.superseded_by is None
                                ):
                                    entry.superseded_by = f"answer:{len(flow.answers)}"
                            flow.ledger.record(
                                field, value, flow.spoken_source, evidence=transcript
                            )
                    persist()
                    log(
                        "clinical_turn",
                        next_question=result.next_question_id,
                        alerted=result.should_alert_staff,
                    )
                    for alert in result.red_flags:
                        if alert.rule_id not in {flag.rule_id for flag in session_red_flags}:
                            session_red_flags.append(alert)

                    if result.should_alert_staff:
                        log("red_flag", rules=[alert.rule_id for alert in result.red_flags])
                        await cancel_tts("red_flag")
                        await send(
                            {
                                "type": "staff.alert",
                                "alerts": [
                                    alert.model_dump(mode="json") for alert in result.red_flags
                                ],
                            }
                        )
                        # Cut straight to the emergency screen from whatever stage we were on, then
                        # still produce the sheet - staff need the details, not just the alarm.
                        flow.check_red_flags(result.red_flags)
                        await finish_session()
                    elif flow.edit_target is not None:
                        flow.edit_target = None
                        flow.edit_return = None
                        flow.stage = Stage.REVIEW
                        pending_question = None
                        await send_screen()
                    elif result.next_question:
                        # The field the next question targets, so the reply to it - even a bare word
                        # or number - binds correctly instead of forcing the extractor to guess.
                        pending_question = QUESTIONS.get(result.next_question_id or "")
                        await cancel_tts("next_question")
                        guard.invalidate_prompt()
                        invalidate_audio()
                        persist()
                        wording = question_text(result.next_question_id or "", result.next_question)
                        await send(
                            {
                                "type": "clinical.question",
                                "id": result.next_question_id,
                                "text": wording,
                                "answer_ui": answer_ui(result.next_question_id or ""),
                                "accumulate": result.next_question_id == "ask_complaint",
                                "allowed_actions": flow.screen(session.state)["allowed_actions"],
                            }
                        )
                        # The interview stage has no headline of its own - the clinical question IS
                        # the screen, same as the wired kiosk shows in edge/runtime.py.
                        show_on_panel(wording)
                        queue_speech(wording, result.language)
                    else:
                        # Hand back to the flow for questionnaires and documents.
                        log("interview_complete")
                        await cancel_tts("interview_complete")
                        if flow.stage is Stage.INTERVIEW:
                            flow.complete_interview()
                        await send_screen()
                except Exception as exc:
                    log("error", stage="clinical")
                    raise RuntimeError("Clinical answer could not be saved") from exc

        def spawn_turn(transcript: str, language: str | None, spoken: bool = True) -> None:
            expected_revision = guard.revision
            expected_session = session_id

            async def guarded_turn() -> None:
                if expected_revision != guard.revision or expected_session != session_id:
                    return
                try:
                    await process_final(
                        transcript,
                        language,
                        spoken=spoken,
                        epoch=(expected_session, expected_revision),
                    )
                except (ValueError, RuntimeError, OSError, sqlite3.Error):
                    await send(
                        {
                            "type": "error",
                            "stage": "flow",
                            "message": "Please use the current prompt",
                        }
                    )

            task = asyncio.create_task(guarded_turn(), name=f"turn-{session_id}")
            turn_tasks.add(task)
            task.add_done_callback(turn_tasks.discard)

        def question_text(question_id: str, template: str) -> str:
            """The opening question is one open prompt, not "what brings you in today?"."""
            if question_id == "ask_complaint":
                return prompt_text("narrative", flow.language or local_language or "en")
            return template

        def narrative_open() -> bool:
            """True while the patient is describing their problem into the box.

            Speech then accumulates on the tablet instead of being dispatched sentence by
            sentence; the whole description is extracted once when they press Proceed, and the
            interview asks only for what that left empty.
            """
            return (
                flow.stage is Stage.INTERVIEW
                and pending_question is not None
                and pending_question.id == "ask_complaint"
                and not flow.restart_confirm
                and not flow.withdraw_confirm
            )

        async def transcribe_local(pcm: bytes) -> tuple[str, str | None]:
            wav_bytes = pcm_to_wav(pcm)
            # Detection helps choose the initial language; only an explicit
            # workflow selection may pin subsequent recognition.
            pin = flow.language or None
            text, detected = await asyncio.to_thread(stt.transcribe, wav_bytes, pin)
            return text, pin or detected

        async def run_local_stt() -> None:
            """Frame the browser's raw PCM into VAD-sized windows and turn-detect locally.

            This is the same energy-gate-and-lock logic proven in medikiosk.edge.runtime: a turn
            below min_utterance_rms is dropped before it ever reaches the recognizer, because
            Whisper invents fluent sentences from silence rather than reporting no speech - on
            pure digital silence it once returned a confident 'you'. That fabricated answer must
            never reach the clinical state machine.
            """

            assert local_vad is not None
            buffer = b""
            generation = audio_generation
            try:
                while True:
                    chunk = await audio_queue.get()
                    if chunk is None:
                        break
                    if generation != audio_generation:
                        buffer = b""
                        generation = audio_generation
                    buffer += chunk
                    while len(buffer) >= FRAME_BYTES:
                        frame, buffer = buffer[:FRAME_BYTES], buffer[FRAME_BYTES:]
                        probability = local_vad.probability(frame)
                        utterance = local_segmenter.feed(probability, frame)
                        if utterance is None:
                            continue
                        if rms(utterance) < active_settings.min_utterance_rms:
                            # Whisper invents fluent speech from silence rather than reporting no
                            # speech, so this turn never reaches it - dropped on energy alone.
                            log(
                                "silent_turn",
                                rms=rms(utterance),
                                floor=active_settings.min_utterance_rms,
                            )
                            await send({"type": "vad", "state": "speech_end", "source": "local"})
                            continue
                        await send({"type": "vad", "state": "speech_end", "source": "local"})
                        generation = audio_generation
                        transcript, language = await transcribe_local(utterance)
                        if generation != audio_generation:
                            buffer = b""
                            continue
                        transcript = transcript.strip()
                        accumulate = bool(
                            transcript
                            and narrative_open()
                            and parse_command(transcript, flow.language) is None
                        )
                        await send(
                            {
                                "type": "transcript.final",
                                "text": transcript,
                                "language": language,
                                "accumulate": accumulate,
                            }
                        )
                        if transcript and not accumulate:
                            spawn_turn(transcript, language)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log("error", stage="stt", error_type=type(exc).__name__)
                await send(
                    {
                        "type": "error",
                        "stage": "stt",
                        "message": (
                            "Offline speech recognition stopped. Use touch or request staff help."
                        ),
                    }
                )

        await send(
            {
                "type": "session.ready",
                "session_id": session_id,
                "audio": {
                    "sample_rate": 16000,
                    "encoding": "linear16",
                    "aec": "browser-webrtc",
                    "noise_suppression": "browser-webrtc",
                    "local_vad": "energy",
                    "server_vad": "saaras" if use_cloud else ("silero" if use_local else "none"),
                },
                "providers": {
                    "openai": active_settings.openai_configured,
                    "sarvam": active_settings.sarvam_configured,
                    "local": use_local,
                },
            }
        )

        def show_on_panel(
            headline: str, options: tuple[str, ...] = (), alert: bool = False
        ) -> None:
            """Draw on the kiosk display, if one is attached. Never raises into an interview."""

            if tablet is None or not headline:
                return
            try:
                from medikiosk.edge.display import Screen, render

                tablet.show(
                    render(
                        Screen(
                            language=(flow.language or active_settings.edge_language)[:2],
                            headline=headline,
                            options=options,
                            alert=alert,
                        ),
                        active_settings.panel_scale,
                    )
                )
            except Exception as exc:
                log("panel_failed", message=str(exc))

        async def send_screen() -> None:
            """Push the current stage to the client, and speak it when there is something to say."""

            nonlocal tts_task
            guard.invalidate_prompt()
            invalidate_audio()
            persist()
            screen = flow.screen(session.state)
            screen.update({"session_id": session_id, "revision": guard.revision})
            await send({"type": "flow.screen", "data": screen})
            log("flow_stage", stage=screen["stage"], input=screen.get("input"))
            show_on_panel(
                screen.get("headline", ""),
                tuple(option["label"] for option in screen.get("options", [])),
                alert=bool(screen.get("alert")),
            )
            headline = screen.get("headline")
            if headline:
                await cancel_tts("flow_stage")
                # Read the choices out too, numbered to match the cards on screen. Speaking only
                # the question leaves a patient who cannot read with no idea what the options are.
                spoken = [headline]
                for index, option in enumerate(screen.get("options") or [], start=1):
                    spoken.append(f"{index}. {option['label']}")
                for index, answer in enumerate(screen.get("review") or [], start=1):
                    outcome = (
                        answer["answer"]
                        if answer["status"] == "answered"
                        else ("उत्तर नहीं दिया" if flow.language == "hi" else "not established")
                    )
                    spoken.append(f"{index}. {answer['question']}. {outcome}")
                queue_speech(". ".join(spoken), flow.language)
            elif screen["stage"] == Stage.INTERVIEW.value:
                if pending_question is None:
                    await ask_current_question()
                else:
                    wording = question_text(
                        pending_question.id, pending_question.template_for(flow.language)
                    )
                    await send(
                        {
                            "type": "clinical.question",
                            "id": pending_question.id,
                            "text": wording,
                            "answer_ui": answer_ui(pending_question.id),
                            "accumulate": pending_question.id == "ask_complaint",
                            "allowed_actions": screen["allowed_actions"],
                        }
                    )
                    await speak(wording)

        def queue_speech(
            text: str, language: str | None, epoch: tuple[str, int] | None = None
        ) -> None:
            nonlocal tts_task, pending_speech
            speech = (text, language, epoch or (session_id, guard.revision))
            if transition_active:
                pending_speech = speech
            else:
                tts_task = asyncio.create_task(stream_tts(*speech), name=f"tts-{session_id}")

        async def speak(text: str) -> None:
            """Say something without changing the screen."""
            await cancel_tts("speak")
            queue_speech(text, flow.language)

        async def watch_idle() -> None:
            """Privacy timeout: warn an untouched kiosk, then close it for the next patient.

            "More time" doubles the allowance; any accepted action resets the clock. The
            language screen never times out because nobody's data is on it yet.
            """
            warned = False
            while True:
                await asyncio.sleep(min(5.0, idle_seconds / 10))
                if flow.stage is Stage.LANGUAGE or transition_active:
                    warned = False
                    continue
                idle = time.monotonic() - last_activity
                warning_at = idle_seconds - min(60.0, idle_seconds / 2)
                if idle >= idle_seconds:
                    log("session_idle_closed", stage=flow.stage.value)
                    with suppress(RuntimeError, OSError):
                        await websocket.close(code=4408, reason="Idle")
                    return
                if idle >= warning_at and not warned:
                    warned = True
                    await send({"type": "session.idle", "remaining": idle_seconds - idle})
                    await speak(prompt_text("idle_warning", flow.language))
                elif idle < warning_at:
                    warned = False

        async def ask_current_question() -> None:
            """Ask the clinical question the state machine wants next, in the chosen language."""

            nonlocal tts_task, pending_question
            question = session.state_machine.next_question(session.state, unresolved)
            if question is None:
                pending_question = None
                if flow.stage is Stage.INTERVIEW:
                    flow.complete_interview()
                    await send_screen()
                return
            attempts[question.id] = attempts.get(question.id, 0) + 1
            if attempts[question.id] > active_settings.max_question_attempts:
                # Leave the field blank rather than trapping the patient. The report lists it
                # under "not established" so the doctor knows it was asked and not answered.
                unresolved.append(question.id)
                log("unresolved", question=question.id)
                await ask_current_question()
                return
            pending_question = question
            guard.invalidate_prompt()
            invalidate_audio()
            persist()
            language = flow.language or local_language
            text = question_text(question.id, question.template_for(language))
            await send(
                {
                    "type": "clinical.question",
                    "id": question.id,
                    "text": text,
                    # Which pictorial control to draw, so a patient who cannot read the
                    # question can still answer it.
                    "answer_ui": answer_ui(question.id),
                    "accumulate": question.id == "ask_complaint",
                    "allowed_actions": flow.screen(session.state)["allowed_actions"],
                    # Set when this is a re-ask of something the last answer did not settle.
                    "clarifying": bool(getattr(question, "clarifying", False)),
                }
            )
            log("asked", question=question.id, language=language)
            show_on_panel(text)
            await cancel_tts("ask_question")
            queue_speech(text, language)

        async def export_to_hospital(built: dict[str, Any]) -> str:
            """Send the finished record to the hospital, if the patient allowed exactly that.

            Returns what to write on the sheet, so a staff member reading a report can tell a
            record that reached the hospital from one that is still only on this Jetson.

            `cloud_intake` is asked for on its own. Permission to be interviewed by a kiosk is
            not permission to transmit the interview, and treating one as the other is the
            failure this branch exists to make impossible.
            """

            api, hospital_id = cloud["api"], cloud["hospital_id"]
            if api is None:
                return "not_requested"
            if hospital_id is None:
                # Provisioned but never reached the cloud: nothing here knows which hospital
                # this token writes into, and guessing is how a record lands in the wrong one.
                # Checked before consent so the sheet never reports a refusal by a patient who
                # was never asked - they were not, because there was nothing to ask about.
                log("cloud_export_skipped", reason="hospital_unknown")
                return "unreachable"
            if not flow.transfer_decided:
                log("cloud_export_skipped", reason="not_asked")
                return "not_asked"
            if not flow.consent.allows("cloud_intake"):
                log("cloud_export_skipped", reason="refused")
                return "declined_by_patient"

            config = cloud["config"]
            record = kiosk_envelope(
                built,
                session_id,
                hospital_id=hospital_id,
                status="complete",
                content_version=hospital_sync.content_version(config),
                kiosk_id=active_settings.kiosk_id or socket.gethostname(),
                engine_version=f"medikiosk-{__version__}",
            )
            department = hospital_sync.department_code(
                config, hospital_id, (built.get("routing") or {}).get("queue")
            )
            if department:
                record["department_code"] = department
            # The session id is the intake id: unique per encounter and stable across a retry,
            # so an ingest repeated after a crash returns the same intake rather than a second.
            response = await asyncio.to_thread(api.ingest, record, session_id)
            body = response.body or {}
            if not response.ok:
                log(
                    "cloud_ingest_failed",
                    outcome=response.outcome.value,
                    status=response.status,
                    detail=response.detail[:200],
                )
                return f"failed:{response.outcome.value}"
            if not body.get("intake_id"):
                log("cloud_ingest_unusable", reason=body.get("reason"))
                return f"unusable:{body.get('reason')}"
            built["hospital_intake_id"] = body["intake_id"]
            log(
                "cloud_ingested",
                intake=body["intake_id"],
                status=body.get("status"),
                repaired=body.get("repaired"),
                needs_review=body.get("needs_review"),
            )
            return "sent"

        async def finish_session() -> None:
            """A saved local report is independent of optional cloud delivery."""
            nonlocal intake_complete
            if intake_complete:
                await send({"type": "flow.report", "data": flow.report})
                return
            if not flow.consent.allows("local_intake") or store is None:
                raise RuntimeError("Consented encrypted storage is required")
            emergency = flow.stage is Stage.EMERGENCY
            if not emergency and flow.stage not in {Stage.REVIEW, Stage.FINALIZING}:
                raise ValueError("Review the intake before finalizing")
            if not emergency:
                flow.stage = Stage.FINALIZING
            # Journal before the separate idempotent report/queue/visit writes.
            # A crash here resumes finalization, never creates a new encounter.
            store.save_workflow(session_id, snapshot(), guard.token)
            built = flow.finish(session.state, session_red_flags)
            built["encounter_id"] = session_id
            built["completion"] = "finalizing"
            built["cloud_status"] = "not_requested"
            built["consent"] = flow.consent.model_dump(mode="json")
            store.save_report(session_id, built)
            entry = queue.assign(session_id, built)
            built["queue_entry"] = {**vars(entry), "state": "WAITING"}
            if flow.abha_number and records is not None and flow.consent.allows("history_linkage"):
                records.save(
                    flow.abha_number,
                    {
                        "complaint": session.state.complaint,
                        "severity": session.state.severity,
                        "queue": built["routing"]["queue"],
                    },
                    encounter_id=session_id,
                )
            built["completion"] = "saved_local"
            flow.report = built
            flow.stage = Stage.EMERGENCY if emergency else Stage.REPORT
            intake_complete = True
            persist()
            # Only now, with the record safely on this disk, is the hospital's copy attempted.
            # A failed export is a delivery problem, never a lost intake: the patient already
            # has a token and staff already have the sheet.
            built["cloud_status"] = await export_to_hospital(built)
            flow.report = built
            persist()
            await send({"type": "flow.report", "data": built})
            log("report_ready", band=entry.band, number=entry.number)
            await send_screen()

        try:
            if restored is not None:
                flow = KioskFlow.from_snapshot(restored["flow"])
                session.state = PatientState.model_validate(restored["state"])
                guard.restore(restored["guard"])
                intake_complete = (
                    restored.get("status") == "complete"
                    and (flow.report or {}).get("completion") == "saved_local"
                )
                local_language = flow.language or local_language
                local_language_locked = bool(flow.language)
                attempts.update(restored.get("attempts", {}))
                pending_question = QUESTIONS.get(restored.get("pending_question_id") or "")
                unresolved.extend(restored.get("unresolved", []))
                session_red_flags.extend(
                    RedFlagAlert.model_validate(a) for a in restored.get("red_flags", [])
                )
                log("session_resumed", stage=flow.stage.value)
            active_sessions[session_id] = {"flow": flow, "guard": guard, "captures": {}}
            log(
                "session_start",
                mode="local" if use_local else "touch-only",
                resumed=restored is not None,
            )
            await send({"type": "session.id", "session_token": guard.token})
            if intake_complete:
                await send({"type": "flow.report", "data": flow.report})
            await send_screen()
            idle_task = asyncio.create_task(watch_idle(), name=f"idle-{session_id}")
            if use_local:
                stt_task = asyncio.create_task(run_local_stt(), name=f"stt-local-{session_id}")
                await send(
                    {
                        "type": "configuration.required",
                        "missing": [],
                        "message": "Local speech is available; no cloud service is used.",
                    }
                )
            else:
                await send(
                    {
                        "type": "configuration.required",
                        "missing": ["local speech service"],
                        "message": (
                            "Offline speech is unavailable. Use touch or request staff help."
                        ),
                    }
                )
            while True:
                incoming = await websocket.receive()
                if incoming.get("bytes") is not None:
                    if len(incoming["bytes"]) > 65536:
                        continue
                    if (
                        use_local
                        and not playback_active
                        and capture_epoch == (session_id, guard.revision)
                        and stt_task is not None
                        and not stt_task.done()
                    ):
                        if audio_queue.full():
                            audio_queue.get_nowait()
                        audio_queue.put_nowait(incoming["bytes"])
                    continue
                if incoming.get("type") == "websocket.disconnect":
                    break
                raw = incoming.get("text")
                if raw is None:
                    continue
                try:
                    command = json.loads(raw)
                    if not isinstance(command, dict):
                        raise ValueError("Expected a JSON object")
                except (ValueError, TypeError):
                    await send({"type": "error", "stage": "protocol", "message": "Invalid command"})
                    continue
                command_type = command.get("type")
                if command_type == "session.stop":
                    break
                if command_type == "audio.start":
                    if (
                        command.get("session_id") == session_id
                        and command.get("revision") == guard.revision
                        and not playback_active
                    ):
                        capture_epoch = (session_id, guard.revision)
                    continue
                if command_type == "playback.state":
                    if (
                        command.get("session_id") == session_id
                        and command.get("revision") == guard.revision
                    ):
                        playback_active = command.get("playing") is True
                        invalidate_audio()
                    continue
                if command_type != "flow.action":
                    await send(
                        {
                            "type": "error",
                            "stage": "protocol",
                            "message": "This client must use workflow protocol 2",
                        }
                    )
                    continue
                try:
                    action = FlowAction.model_validate(command)
                    if not guard.check(action):
                        await send(
                            {"type": "flow.ack", "action_id": action.action_id, "duplicate": True}
                        )
                        continue
                    for task in list(turn_tasks):
                        task.cancel()
                    if turn_tasks:
                        await asyncio.gather(*list(turn_tasks), return_exceptions=True)
                    await cancel_tts("action")
                    invalidate_audio()
                    if (
                        flow.stage is Stage.INTERVIEW
                        and not flow.restart_confirm
                        and not flow.withdraw_confirm
                        and action.action in {"answer", "choose"}
                    ):
                        if action.question_id and (
                            pending_question is None or action.question_id != pending_question.id
                        ):
                            raise ValueError("Question changed")
                        value = "" if action.value is None else str(action.value)
                        await process_final(value, flow.language, spoken=False, action=action)
                    else:
                        async with transition(action=action):
                            await handle_action(action.action, action.value, action.question_id)
                    await send(
                        {"type": "flow.ack", "action_id": action.action_id, "duplicate": False}
                    )
                except (ValueError, RuntimeError, OSError, sqlite3.Error):
                    await send(
                        {
                            "type": "error",
                            "stage": "flow",
                            "action_id": command.get("action_id"),
                            "message": "Action not saved; please use the current prompt",
                        }
                    )
        except WebSocketDisconnect:
            log("session_disconnect")
        except RuntimeError as exc:
            # A tablet that sleeps, loses the USB link, or is killed from the recents screen closes
            # the socket without a clean handshake. Starlette then raises RuntimeError('Cannot call
            # "receive" once a disconnect message has been received') rather than
            # WebSocketDisconnect, which dumped a traceback into the intake log on every such exit
            # and made real errors hard to spot.
            if "disconnect message has been received" not in str(exc):
                raise
            log("session_disconnect", detail="client vanished without a close frame")
        finally:
            with suppress(asyncio.QueueFull):
                audio_queue.put_nowait(None)
            with suppress(WebSocketDisconnect, RuntimeError, OSError):
                await cancel_tts("session_end")
            for task in turn_tasks:
                task.cancel()
            if turn_tasks:
                await asyncio.gather(*turn_tasks, return_exceptions=True)
            if stt_task:
                stt_task.cancel()
                await asyncio.gather(stt_task, return_exceptions=True)
            if idle_task:
                # Only ever sleeping; nothing to wait for.
                idle_task.cancel()
            active_sessions.pop(session_id, None)
            leased_tokens.discard(guard.token)
            if not intake_complete:
                with suppress(OSError, RuntimeError):
                    persist()
            else:
                resume_states.pop(guard.token, None)
            log("session_end")

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run("medikiosk.app:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
