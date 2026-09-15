import asyncio
import base64
import contextlib
import io
import json
import time
import uuid
import wave
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from medikiosk.clinical.answers import AFFIRMATIVE
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
from medikiosk.kiosk import extraction, handwriting
from medikiosk.kiosk.abha import VisitRecords, from_qr_payload, normalise
from medikiosk.kiosk.document_outbox import DocumentOutbox, infer_kind
from medikiosk.kiosk.flow import KioskFlow, Stage
from medikiosk.kiosk.queue import QueueStore, load_specialties
from medikiosk.languages import LANGUAGES
from medikiosk.providers.intake_api import IntakeApi, kiosk_envelope, load_token, redacted
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
    """Whether a reply confirms. Accepts every supported language, plus English alongside it,
    because patients mix "yes" and "haan" freely - the same vocabulary direct_answer() uses."""

    words = {word.strip(" .,!?।॥") for word in transcript.lower().split()}
    return any(words & vocabulary for vocabulary in AFFIRMATIVE.values())

# Clinical fields worth attributing on the doctor's sheet. Free-text transcripts are already
# kept verbatim, so only the extracted values need a source recorded against them.
PROVENANCE_FIELDS = (
    "complaint", "duration", "severity", "age_years",
    "fever", "vomiting", "breathlessness", "chest_pain", "pain_radiation",
    "sweating", "active_bleeding", "altered_consciousness",
    "one_sided_weakness", "speech_difficulty",
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

        extractor: Any = OpenAIClinicalExtractor(settings.openai_api_key or "", settings.openai_model)
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
    voices = VoiceBank(
        active_settings.piper_binary,
        active_settings.voice_dir,
        active_settings.flite_binary,
        active_settings.flite_voice_dir,
        active_settings.prerendered_audio_dir,
    )
    ocr_model: dict[str, Any] = {"instance": None}
    # Handwritten pages are held here between the scan and the moment the record exists.
    outbox = DocumentOutbox(active_settings.session_store_path.parent / "outbox")
    # The cloud reader is opt-in and needs a provisioned token. Without both, every page stays
    # on the Jetson exactly as before - the outbox is never written to.
    intake_api: IntakeApi | None = None
    if active_settings.handwritten_cloud_ocr:
        kiosk_token = load_token(active_settings.intake_token_path)
        if kiosk_token:
            intake_api = IntakeApi(kiosk_token, active_settings.intake_api_url)
            emit_log_line({"event": "cloud_ocr_enabled", "token": redacted(kiosk_token)})
        else:
            emit_log_line({"event": "cloud_ocr_unprovisioned",
                           "message": "handwritten_cloud_ocr is on but no kiosk token was found"})
    ocr_lock = asyncio.Lock()
    # The receiving half of the product: a report nobody can read is not a finished intake.
    queue = QueueStore(active_settings.session_store_path.with_name("queue.db"))
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
            print(f"kiosk display unavailable on :{active_settings.panel_port}: {error}", flush=True)
            tablet = None

    llm_extractor = (
        LocalLLMClinicalExtractor(active_settings.clinical_llm_model, active_settings.ollama_url)
        if active_settings.clinical_llm_enabled
        else None
    )

    def local_speech_ready() -> bool:
        return whisper.health()

    def clinical_session() -> ClinicalSession:
        llm = llm_extractor if llm_extractor and llm_extractor.health() else None
        return _clinical_session(active_settings, llm)

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
                "languages": sorted(LANGUAGES),
            },
            "storage": {"encrypted": store is not None},
        }

    @app.post("/api/demo-turn")
    async def demo_turn(request: DemoTurnRequest) -> dict[str, Any]:
        session = await asyncio.to_thread(clinical_session)
        result = await session.process_transcript(request.transcript, request.language)
        return result.model_dump(mode="json")

    @app.post("/api/ocr")
    async def ocr(image: UploadFile) -> dict[str, Any]:
        """Read one photographed document. Loads the recognizer once and keeps it resident."""

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
            workdir.mkdir(parents=True, exist_ok=True)
            photo = workdir / f"{uuid.uuid4().hex}.jpg"
            try:
                photo.write_bytes(payload)
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
        if verdict.handwritten and intake_api is not None:
            outbox_handle = outbox.hold(payload, infer_kind(structured), verdict.reason)

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
        return {
            "lines": lines,
            "text": "\n".join(lines),
            "seconds": round(elapsed, 2),
            "handwritten": verdict.handwritten,
            "confidence_note": verdict.reason,
            "outbox_handle": outbox_handle,
        }

    @app.post("/api/abha-scan")
    async def abha_scan(image: UploadFile) -> dict[str, Any]:
        """Decode an ABHA QR from a photographed card.

        The decoding happens here rather than in the tablet app so the app needs no zbar build:
        OpenCV's detector is already installed on this device and proven against the same cards.
        """

        from PIL import Image

        from medikiosk.kiosk.abha import scan_qr

        try:
            photo = Image.open(io.BytesIO(await image.read())).convert("RGB")
        except (OSError, ValueError) as exc:
            raise HTTPException(422, "Upload a readable image") from exc
        number = await asyncio.to_thread(scan_qr, photo)
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
    async def api_queue() -> dict[str, Any]:
        """The OPD list. Review cases first - they are not merely high priority."""

        entries = queue.waiting()
        return {
            "specialties": specialties,
            "review": [vars(e) for e in entries if e.needs_review],
            "waiting": [vars(e) for e in entries if not e.needs_review],
        }

    @app.get("/api/encounters/{encounter_id}")
    async def api_encounter(encounter_id: str) -> dict[str, Any]:
        report = load_report(encounter_id)
        if report is None:
            return {"error": "unknown encounter"}
        entry = queue.get(encounter_id)
        return {"encounter_id": encounter_id, "queue": vars(entry) if entry else None,
                "report": report}

    @app.post("/api/encounters/{encounter_id}/state")
    async def api_set_state(encounter_id: str, body: dict) -> dict[str, Any]:
        """Doctor lifecycle: WAITING to IN_CONSULTATION to COMPLETED."""

        state = str(body.get("state", "")).upper()
        if state not in ("WAITING", "IN_CONSULTATION", "COMPLETED"):
            return {"error": f"unknown state {state!r}"}
        queue.set_state(encounter_id, state)
        print(json.dumps({"event": "queue_state", "encounter": encounter_id[:8], "state": state}),
              flush=True)
        return {"ok": True, "state": state}

    @app.post("/api/encounters/{encounter_id}/correct")
    async def api_correct(encounter_id: str, body: dict) -> dict[str, Any]:
        """A clinician fixing a value. Supersedes rather than overwrites, so the original stays."""

        report = load_report(encounter_id)
        if report is None:
            return {"error": "unknown encounter"}
        key, value = str(body.get("key", "")), body.get("value")
        by = str(body.get("by", "clinician"))
        if not key:
            return {"error": "key required"}
        entries = report.setdefault("provenance", {}).setdefault("entries", [])
        entries.append({
            "key": key, "value": value, "source": "DOCTOR_VERIFIED",
            "confidence": None, "evidence": body.get("evidence"),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "superseded_by": None, "corrected_by": by,
        })
        for entry in entries[:-1]:
            if entry.get("key") == key and entry.get("superseded_by") is None:
                entry["superseded_by"] = by
        if store is not None:
            store.save_report(encounter_id, report)
        print(json.dumps({"event": "correction", "encounter": encounter_id[:8], "key": key}),
              flush=True)
        return {"ok": True}

    @app.websocket("/ws/session")
    async def voice_session(websocket: WebSocket) -> None:
        await websocket.accept()
        # A tablet that lost power or dropped its link reconnects with its session id and
        # continues. An intake takes minutes, and making a patient in pain start again because
        # the Wi-Fi blinked is the difference between a demo and something usable in an OPD.
        # Read from the raw ASGI scope rather than websocket.query_params: the two Starlette
        # versions in use here (1.3 locally, 1.6 on the Jetson) do not agree on the latter for
        # websockets, and the resume silently stopped working on the device.
        resumed = parse_qs(websocket.scope.get("query_string", b"").decode()).get(
            "resume", [None]
        )[0]
        session_id = resumed if resumed else str(uuid.uuid4())
        session = await asyncio.to_thread(clinical_session)
        audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=80)
        send_lock = asyncio.Lock()
        turn_tasks: set[asyncio.Task[Any]] = set()
        stt_task: asyncio.Task[Any] | None = None
        tts_task: asyncio.Task[Any] | None = None
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
        # A voice answer is repeated back before it is acted on. Whisper mishears short words
        # in a noisy OPD, and a patient who cannot read has no other way to catch it.
        awaiting_confirmation: str | None = None
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
            emit_log_line({"session": session_id[:8], "event": event, **fields})

        # Cloud (Sarvam) takes priority if it is genuinely configured; this device has no Sarvam
        # key, so every session on this Jetson runs the local branch - the same Whisper + Piper
        # stack proven in medikiosk.edge.runtime, driven by network audio instead of a local mic.
        use_cloud = active_settings.sarvam_configured
        use_local = not use_cloud and await asyncio.to_thread(local_speech_ready)
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

        async def send(payload: dict[str, Any]) -> None:
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

        async def stream_tts(text: str, language: str | None) -> None:
            if use_cloud:
                from medikiosk.providers.sarvam_provider import SarvamStreamingTTS

                synthesizer = SarvamStreamingTTS(
                    active_settings.sarvam_api_key or "",
                    active_settings.sarvam_tts_speaker,
                )
                await send({"type": "tts.start", "sample_rate": 24000})
                try:
                    async for pcm in synthesizer.stream(
                        text,
                        language or active_settings.sarvam_tts_language,
                    ):
                        await send(
                            {
                                "type": "tts.audio",
                                "encoding": "linear16",
                                "sample_rate": 24000,
                                "audio": base64.b64encode(pcm).decode("ascii"),
                            }
                        )
                    await send({"type": "tts.end"})
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await send({"type": "error", "stage": "tts", "message": str(exc)})
                return

            if not use_local:
                return
            lang = language or local_language
            if lang not in LANGUAGES or not voices.available(lang):
                lang = active_settings.edge_language
            await send({"type": "tts.start", "sample_rate": 0})
            try:
                # Piper/Flite are subprocess calls; off the event loop so one synthesis does not
                # stall every other message this connection needs to send.
                wav_bytes = await asyncio.to_thread(voices.synthesize, text, lang)
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
            except Exception as exc:
                await send({"type": "error", "stage": "tts", "message": str(exc)})

        turn_lock = asyncio.Lock()
        audio_generation = 0

        async def process_final(
            transcript: str, language: str | None, spoken: bool = True
        ) -> None:
            async with turn_lock:
                nonlocal tts_task, pending_question, intake_complete
                if flow.stage is not Stage.INTERVIEW:
                    # Speech before the interview stage is not an answer to anything - it is a patient
                    # greeting the kiosk, or someone talking nearby. Feeding it to the extractor made
                    # "Namaste" come back as a chief complaint of "ear pain" and consumed the first
                    # question without ever asking it.
                    log("ignored_off_stage", text=transcript, stage=flow.stage.value)
                    return
                if intake_complete:
                    # The state machine is done; nothing downstream would act on this. Drop it here so
                    # a patient still chatting after the closing prompt is not silently transcribed
                    # into a record no one reads.
                    log("ignored_after_close", text=transcript)
                    return
                nonlocal awaiting_confirmation
                spoken_language = (flow.language or local_language or "en")[:2]

                if awaiting_confirmation is not None:
                    answer, awaiting_confirmation = awaiting_confirmation, None
                    if _is_yes(transcript):
                        log("confirmed", text=answer)
                        transcript = answer
                    else:
                        # Not a yes: discard what was heard and ask the same question again rather
                        # than recording a value the patient did not agree to.
                        log("confirm_rejected", heard=answer)
                        await speak(prompt_text("confirm_retry", spoken_language))
                        pending_question = None
                        await ask_current_question()
                        return

                elif spoken and flow.stage is Stage.INTERVIEW and pending_question is not None:
                    awaiting_confirmation = transcript
                    log("confirming", text=transcript)
                    await speak(
                        prompt_text("confirm_heard", spoken_language).replace("{answer}", transcript)
                    )
                    return

                asked = pending_question
                log("transcript", text=transcript, language=language, asked=asked.id if asked else None)
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
                            question = session.state_machine.next_question(session.state, unresolved)
                            result.next_question_id = question.id if question else None
                            result.next_question = question.template_for(flow.language) if question else None
                            if question:
                                attempts[question.id] = attempts.get(question.id, 0) + 1
                    if store is not None:
                        try:
                            store.save(session_id, result.state)
                        except Exception as exc:
                            log("storage_failed", message=str(exc))
                    await send({"type": "clinical.turn", "data": result.model_dump(mode="json")})
                    # Record what this turn established, attributed to whoever is speaking. A relative
                    # answering for the patient is reporting second-hand, and the doctor's sheet says
                    # so rather than presenting it as the patient's own words.
                    for field in PROVENANCE_FIELDS:
                        value = getattr(result.state, field, None)
                        if value is not None and flow.ledger.current(field) is None:
                            flow.ledger.record(
                                field, value, flow.spoken_source, evidence=transcript
                            )
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
                                "alerts": [alert.model_dump(mode="json") for alert in result.red_flags],
                            }
                        )
                        # Cut straight to the emergency screen from whatever stage we were on, then
                        # still produce the sheet - staff need the details, not just the alarm.
                        flow.check_red_flags(result.red_flags)
                        await finish_session()
                    elif result.next_question:
                        # The field the next question targets, so the reply to it - even a bare word
                        # or number - binds correctly instead of forcing the extractor to guess.
                        pending_question = QUESTIONS.get(result.next_question_id or "")
                        await cancel_tts("next_question")
                        await send({"type": "clinical.question", "id": result.next_question_id,
                                    "text": result.next_question,
                                    "answer_ui": answer_ui(result.next_question_id or "")})
                        # The interview stage has no headline of its own - the clinical question IS
                        # the screen, same as the wired kiosk shows in edge/runtime.py.
                        show_on_panel(result.next_question)
                        tts_task = asyncio.create_task(
                            stream_tts(result.next_question, result.language),
                            name=f"tts-{session_id}",
                        )
                    else:
                        # The clinical interview is done, but the workflow is not: the Ayurvedic
                        # questionnaire and document scan come after it. Hand back to the flow rather
                        # than ending here.
                        log("interview_complete")
                        await cancel_tts("interview_complete")
                        if flow.stage is Stage.INTERVIEW:
                            flow.advance()
                        await send_screen()
                except Exception as exc:
                    log("error", stage="clinical", message=str(exc))
                    await send({"type": "error", "stage": "clinical", "message": str(exc)})

        def spawn_turn(transcript: str, language: str | None, spoken: bool = True) -> None:
            task = asyncio.create_task(
                process_final(transcript, language, spoken=spoken),
                name=f"turn-{session_id}",
            )
            turn_tasks.add(task)
            task.add_done_callback(turn_tasks.discard)

        async def on_stt_event(event: dict[str, Any]) -> None:
            event_name = event.get("event") or event.get("type") or "unknown"
            if event_name == "vad.speech_start":
                await cancel_tts("barge_in")
                await send({"type": "vad", "state": "speech_start", "source": "saaras"})
            elif event_name == "vad.speech_end":
                await send({"type": "vad", "state": "speech_end", "source": "saaras"})
            elif event_name == "transcript.partial":
                await send(
                    {
                        "type": "transcript.partial",
                        "text": event.get("text", ""),
                        "language": event.get("language"),
                    }
                )
            elif event_name == "transcript.final":
                transcript = str(event.get("text", "")).strip()
                language = event.get("language") or active_settings.sarvam_stt_language
                await send({"type": "transcript.final", "text": transcript, "language": language})
                if transcript:
                    spawn_turn(transcript, language)
            elif event_name == "error":
                await send(
                    {
                        "type": "error",
                        "stage": "stt",
                        "message": event.get("message", "Sarvam realtime error"),
                        "fatal": event.get("is_fatal", False),
                    }
                )

        async def run_stt() -> None:
            from medikiosk.providers.sarvam_provider import SarvamRealtimeSTT

            recognizer = SarvamRealtimeSTT(
                active_settings.sarvam_api_key or "",
                active_settings.sarvam_stt_language,
            )
            try:
                await recognizer.run(audio_queue, on_stt_event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await send({"type": "error", "stage": "stt", "message": str(exc)})

        async def transcribe_local(pcm: bytes) -> tuple[str, str | None]:
            nonlocal local_language, local_language_locked
            wav_bytes = pcm_to_wav(pcm)
            pin = local_language if local_language_locked else None
            text, detected = await asyncio.to_thread(whisper.transcribe, wav_bytes, pin)
            if not local_language_locked and text and detected in LANGUAGES:
                if voices.available(detected):
                    local_language = detected
                local_language_locked = True
            return text, local_language

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
            try:
                while True:
                    chunk = await audio_queue.get()
                    if chunk is None:
                        break
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
                            log("silent_turn", rms=rms(utterance), floor=active_settings.min_utterance_rms)
                            await send({"type": "vad", "state": "speech_end", "source": "local"})
                            continue
                        await send({"type": "vad", "state": "speech_end", "source": "local"})
                        generation = audio_generation
                        transcript, language = await transcribe_local(utterance)
                        if generation != audio_generation:
                            buffer = b""
                            continue
                        transcript = transcript.strip()
                        await send(
                            {"type": "transcript.final", "text": transcript, "language": language}
                        )
                        if transcript:
                            spawn_turn(transcript, language)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log("error", stage="stt", message=str(exc))
                await send({"type": "error", "stage": "stt", "message": str(exc)})

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

        def show_on_panel(headline: str, options: tuple[str, ...] = (), alert: bool = False) -> None:
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
            screen = flow.screen(session.state)
            await send({"type": "flow.screen", "data": screen})
            log("flow_stage", stage=screen["stage"], input=screen.get("input"))
            show_on_panel(
                screen.get("headline", ""),
                tuple(option["label"] for option in screen.get("options", [])),
                alert=bool(screen.get("alert")),
            )
            headline = screen.get("headline")
            if headline and screen["stage"] != Stage.INTERVIEW.value:
                await cancel_tts("flow_stage")
                # Read the choices out too, numbered to match the cards on screen. Speaking only
                # the question leaves a patient who cannot read with no idea what the options are.
                spoken = [headline]
                for index, option in enumerate(screen.get("options") or [], start=1):
                    spoken.append(f"{index}. {option['label']}")
                tts_task = asyncio.create_task(
                    stream_tts(". ".join(spoken), flow.language), name=f"tts-{session_id}"
                )
            elif screen["stage"] == Stage.INTERVIEW.value and pending_question is None:
                # The interview screen has no headline of its own, so arriving here used to leave
                # the kiosk silent until the patient guessed they should talk - and whatever they
                # said was then treated as the answer to a question nobody had asked.
                await ask_current_question()

        async def speak(text: str) -> None:
            """Say something without changing the screen."""

            nonlocal tts_task
            await cancel_tts("speak")
            tts_task = asyncio.create_task(
                stream_tts(text, flow.language), name=f"tts-{session_id}"
            )

        async def ask_current_question() -> None:
            """Ask the clinical question the state machine wants next, in the chosen language."""

            nonlocal tts_task, pending_question
            question = session.state_machine.next_question(session.state, unresolved)
            if question is None:
                pending_question = None
                if flow.stage is Stage.INTERVIEW:
                    flow.advance()
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
            language = flow.language or local_language
            text = question.template_for(language)
            await send(
                {
                    "type": "clinical.question",
                    "id": question.id,
                    "text": text,
                    # Which pictorial control to draw, so a patient who cannot read the
                    # question can still answer it.
                    "answer_ui": answer_ui(question.id),
                    # Set when this is a re-ask of something the last answer did not settle.
                    "clarifying": bool(getattr(question, "clarifying", False)),
                }
            )
            log("asked", question=question.id, language=language)
            show_on_panel(text)
            await cancel_tts("ask_question")
            tts_task = asyncio.create_task(stream_tts(text, language), name=f"tts-{session_id}")

        def submit_held_documents(record: dict[str, Any], handles: list[str]) -> dict[str, Any]:
            """Ingest the record, then upload this session's held pages against its intake_id.

            Ingest is idempotent on the session id, so a retry after a crash returns the same
            intake. The uploads are not - the outbox enforces that an ambiguous send is never
            repeated, so calling this twice cannot duplicate a document.
            """

            assert intake_api is not None
            # The session id is the intake id: a UUID, unique per session, known before the
            # scan stage, and the same key a retry of this session would reuse.
            ingested = intake_api.ingest(kiosk_envelope(record, session_id),
                                         idempotency_key=session_id)
            if not ingested.ok:
                log("cloud_ingest_failed", outcome=ingested.outcome.value,
                    status=ingested.status, detail=ingested.detail[:200])
                return {"ingest": ingested.outcome.value, "documents": []}
            body = ingested.body or {}
            intake_id = body.get("intake_id")
            if not intake_id:
                # The API filed the record as unusable and says why. Nothing exists to attach
                # a document to, so the held pages stay pending and the reason goes on the sheet.
                log("cloud_ingest_unusable", reason=body.get("reason"),
                    errors=[e.get("msg") for e in body.get("errors", [])][:5])
                return {"ingest": "unusable", "reason": body.get("reason"),
                        "errors": body.get("errors", [])[:5], "documents": []}

            results = outbox.submit(intake_api, str(intake_id), handles)
            summary = [
                {"handle": d.handle, "kind": d.kind, "state": d.state,
                 "document_id": d.document_id, "detail": d.detail[:120]}
                for d in results
            ]
            log("cloud_documents", intake_id=str(intake_id),
                states={d.state: sum(1 for r in results if r.state == d.state) for d in results})
            return {"ingest": "ok", "intake_id": str(intake_id), "documents": summary}

        async def finish_session() -> None:
            """Build the doctor's sheet and, for a returning patient, file this visit under it."""

            nonlocal intake_complete
            intake_complete = True
            built = flow.finish(session.state, session_red_flags)
            if flow.abha_number and records is not None:
                try:
                    records.save(
                        flow.abha_number,
                        {
                            "complaint": session.state.complaint,
                            "severity": session.state.severity,
                            "queue": built["routing"]["queue"],
                        },
                    )
                except Exception as exc:  # a storage fault must not lose the patient's report
                    log("visit_save_failed", message=str(exc))
            # Hand the finished intake to the OPD. Until this existed the kiosk produced a
            # report and then had nowhere to send it.
            reports[session_id] = built
            entry = queue.assign(session_id, built)
            built["queue_entry"] = vars(entry)
            # Handwritten pages held during the scan stage go to the cloud reader now that the
            # record exists to attach them to. Off the event loop: it is network I/O, and a slow
            # link must not stall the report the patient is waiting for. Nothing here can raise
            # into the session - a failed upload is recorded on the document, not thrown.
            if intake_api is not None and flow.held_document_handles:
                built["cloud_documents"] = await asyncio.to_thread(
                    submit_held_documents, built, flow.held_document_handles
                )
            if store is not None:
                try:
                    store.save_report(session_id, built)
                except Exception as exc:
                    log("report_save_failed", message=str(exc))
                    built["persistence_error"] = "Report is only available until the kiosk restarts"
            await send({"type": "flow.report", "data": built})
            log(
                "report_ready",
                queue=built["routing"]["queue"],
                band=entry.band,
                number=entry.number,
                stage=flow.stage.value,
            )
            await send_screen()

        restored = resume_states.pop(session_id, None) if resumed else None
        if restored is not None:
            flow, session.state = restored["flow"], restored["state"]
            local_language = flow.language or local_language
            local_language_locked = bool(flow.language) or not active_settings.auto_detect_language
            attempts.update(restored.get("attempts", {}))
            unresolved.extend(restored.get("unresolved", []))
            session_red_flags.extend(restored.get("red_flags", []))
            log("session_resumed", stage=flow.stage.value)

        log(
            "session_start",
            mode="cloud" if use_cloud else ("local" if use_local else "typed-only"),
            resumed=restored is not None,
        )
        await send({"type": "session.id", "session_id": session_id})
        await send_screen()

        if use_cloud:
            stt_task = asyncio.create_task(run_stt(), name=f"stt-{session_id}")
        elif use_local:
            stt_task = asyncio.create_task(run_local_stt(), name=f"stt-local-{session_id}")
            await send({"type": "configuration.required", "missing": [], "message": (
                f"Microphone is live via the on-device Whisper + {active_settings.edge_language} "
                "voice. No cloud key configured or needed."
            )})
        else:
            await send(
                {
                    "type": "configuration.required",
                    "missing": ["SARVAM_API_KEY", "local Whisper server"],
                    "message": (
                        "Microphone STT/TTS is disabled; typed transcript testing remains "
                        "available."
                    ),
                }
            )

        try:
            while True:
                incoming = await websocket.receive()
                if incoming.get("bytes") is not None:
                    if (use_cloud or use_local) and stt_task is not None and not stt_task.done():
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
                expected_stage = {
                    "flow.language": Stage.LANGUAGE, "flow.abha": Stage.ABHA,
                    "flow.who": Stage.WHO, "flow.ayurveda": Stage.AYURVEDA,
                    "flow.prakriti": Stage.PRAKRITI, "flow.document": Stage.DOCUMENTS,
                }.get(command_type)
                if expected_stage is not None and flow.stage is not expected_stage:
                    await send({"type": "error", "stage": "flow", "message": "Stale stage action"})
                    continue
                if command_type in ("flow.restart", "flow.back", "flow.next"):
                    for task in list(turn_tasks):
                        task.cancel()
                    if turn_tasks:
                        await asyncio.gather(*list(turn_tasks), return_exceptions=True)
                    await cancel_tts("navigation")
                    audio_generation += 1
                    local_segmenter.reset()
                    if local_vad is not None:
                        local_vad.reset()
                    while not audio_queue.empty():
                        audio_queue.get_nowait()
                if command_type == "transcript.submit":
                    transcript = str(command.get("text", "")).strip()
                    if transcript:
                        # Typed, not heard: no read-back needed.
                        spawn_turn(transcript, flow.language or command.get("language", "en-IN"), spoken=False)
                elif command_type == "barge_in":
                    await cancel_tts("browser_vad")
                    await send({"type": "vad", "state": "speech_start", "source": "browser"})
                elif command_type == "flow.language":
                    try:
                        flow.choose_language(str(command.get("value", "")))
                    except ValueError as exc:
                        await send({"type": "error", "stage": "language", "message": str(exc)})
                    else:
                        # An explicit choice beats auto-detection: Whisper guessed English from a
                        # one-word "Namaste" and then decoded every Hindi answer as English.
                        local_language = flow.language or local_language
                        local_language_locked = True
                        # The adaptive session renders its own question text, so it needs the
                        # chosen language before the first question is drawn. Without this the
                        # opening question arrived in the configured default and only corrected
                        # itself once the patient had answered it.
                        if hasattr(session, "language"):
                            session.language = local_language
                        log("language_selected", language=local_language)
                        await send_screen()
                elif command_type == "flow.abha":
                    raw_value = str(command.get("value") or "")
                    number = normalise(raw_value) or from_qr_payload(raw_value)
                    if raw_value.strip() and number is None:
                        await send({"type": "error", "stage": "abha", "message": "Enter a valid 14-digit ABHA number or skip"})
                        continue
                    history = records.history(number) if (number and records) else []
                    if number and store:
                        # Prakriti does not change, so a patient who answered it on any previous
                        # visit is never asked again.
                        with contextlib.suppress(Exception):
                            flow.load_prakriti(store.load_prakriti(number))
                    flow.set_abha(number, history)
                    log("abha", matched=bool(number), previous_visits=len(history))
                    await send_screen()
                elif command_type == "flow.who":
                    if command.get("value") not in ("self", "other"):
                        await send({"type": "error", "stage": "who", "message": "Choose patient or representative"})
                        continue
                    flow.set_who(command["value"])
                    await send_screen()
                elif command_type == "flow.ayurveda":
                    try:
                        flow.answer_ayurveda(
                            str(command.get("question_id", "")), str(command.get("value", ""))
                        )
                    except ValueError as exc:
                        await send({"type": "error", "stage": "ayurveda", "message": str(exc)})
                    else:
                        await send_screen()
                elif command_type == "flow.prakriti":
                    # One command for both halves of the stage: the gate answer ("have you filled
                    # this before?") carries no question_id, an actual answer does.
                    try:
                        if command.get("question_id"):
                            flow.answer_prakriti(
                                str(command["question_id"]), str(command.get("value", ""))
                            )
                        else:
                            flow.answer_prakriti_gate(str(command.get("value", "")))
                    except ValueError as exc:
                        await send({"type": "error", "stage": "prakriti", "message": str(exc)})
                    else:
                        if flow.prakriti_record is not None and flow.abha_number and store:
                            # Once in a lifetime means it has to outlive the session, and only an
                            # ABHA gives a later visit anything to look it up by.
                            with contextlib.suppress(Exception):
                                store.save_prakriti(flow.abha_number, flow.prakriti_record)
                        await send_screen()
                elif command_type == "flow.document":
                    handle = command.get("outbox_handle")
                    # Only accept a handle the outbox actually issued. A client cannot make the
                    # kiosk upload an arbitrary file by naming a path.
                    if handle is not None and outbox.get(str(handle)) is None:
                        handle = None
                    flow.add_document(
                        [str(line) for line in (command.get("lines") or [])],
                        command.get("seconds"),
                        handwritten=command.get("handwritten"),
                        outbox_handle=str(handle) if handle else None,
                    )
                    await send_screen()
                elif command_type == "flow.next":
                    # Skip / done: the patient declined this stage, or finished scanning.
                    if flow.stage is Stage.REPORT:
                        pass
                    elif flow.advance() is Stage.REPORT:
                        await finish_session()
                    else:
                        await send_screen()
                elif command_type == "flow.repeat":
                    # Say the current screen again. For a patient who cannot read, the spoken
                    # question is the only version of it there is.
                    if flow.stage is Stage.INTERVIEW and pending_question is not None:
                        await speak(pending_question.template_for(flow.language))
                    else:
                        await send_screen()
                elif command_type == "flow.back":
                    flow.back()
                    pending_question = None
                    await send_screen()
                elif command_type == "flow.restart":
                    session_id = str(uuid.uuid4())
                    # Start a whole new patient. A kiosk gets walked away from mid-intake, and the
                    # next person must not inherit the last one's answers.
                    flow = KioskFlow()
                    session = await asyncio.to_thread(clinical_session)
                    session_red_flags.clear()
                    attempts.clear()
                    unresolved.clear()
                    awaiting_confirmation = None
                    await send({"type": "session.id", "session_id": session_id})
                    pending_question = None
                    intake_complete = False
                    local_language_locked = not active_settings.auto_detect_language
                    local_language = active_settings.edge_language
                    log("session_restart")
                    await send_screen()
                elif command_type == "client.log":
                    # The tablet app has no console anyone can read, so its failures are reported
                    # here and land in the same log as everything else.
                    log("client", message=str(command.get("message", ""))[:400])
                elif command_type == "session.stop":
                    break
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
            if not intake_complete:
                # Only unfinished intakes are worth resuming; a completed one is in the queue.
                resume_states[session_id] = {"flow": flow, "state": session.state,
                                             "attempts": attempts, "unresolved": unresolved,
                                             "red_flags": session_red_flags}
            log("session_end", final_state=session.state.model_dump(mode="json"))

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run("medikiosk.app:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
