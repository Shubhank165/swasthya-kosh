"""Fully offline conversational intake loop for the Jetson kiosk.

Signal path:

    PulseAudio AEC source -> Silero VAD -> utterance segmentation -> local IndicConformer ASR
    -> deterministic extractor -> clinical state machine -> deterministic red-flag rules
    -> question template -> local Flite TTS -> PulseAudio AEC sink

Echo cancellation, noise suppression, and the high-pass filter come from PulseAudio's WebRTC
`module-echo-cancel`; `scripts/setup_jetson_audio.sh` loads it. Nothing in this loop contacts the
internet, and no generative model chooses a question, an urgency, or a clinical fact.
"""

from __future__ import annotations

import argparse
import array
import asyncio
import io
import json
import math
import subprocess
import sys
import threading
import time
import uuid
import wave
from pathlib import Path

from medikiosk.clinical.heuristic import HeuristicClinicalExtractor
from medikiosk.clinical.hybrid import HybridClinicalExtractor
from medikiosk.clinical.questions import QUESTIONS, TemplateQuestionNaturalizer
from medikiosk.clinical.translations import prompt as prompt_text
from medikiosk.config import Settings, get_settings
from medikiosk.edge.display import alert_screen, prompt_screen, question_screen
from medikiosk.edge.vad import FRAME_BYTES, SAMPLE_RATE, SileroVAD, SpeechSegmenter
from medikiosk.languages import LANGUAGES, profile
from medikiosk.providers.local_llm_provider import LocalLLMClinicalExtractor
from medikiosk.providers.voices import VoiceBank
from medikiosk.providers.whisper_provider import WhisperCppSTT
from medikiosk.session import ClinicalSession
from medikiosk.storage import EncryptedSessionStore


class PanelView:
    """The kiosk screen, if one is attached.

    Every call is best-effort: a patient interview must not end because a display cable is loose,
    so a panel fault disables the screen and lets the conversation continue.
    """

    def __init__(self, enabled: bool, emit, target: str = "spi", scale: int = 4) -> None:
        self.panel = None
        self.scale = 1
        self._emit = emit
        if not enabled:
            return
        try:
            if target == "tablet":
                from medikiosk.edge.tablet import TabletPanel, usb_address

                self.panel = TabletPanel(port=8800, scale=scale)
                self.scale = scale
                self.panel.open()
                self._emit("panel_ready", target="tablet", url=f"http://{usb_address()}:8800/")
            else:
                from medikiosk.edge.panel import KioskPanel

                self.panel = KioskPanel()
                self.panel.open()
        except Exception as error:
            self._emit("panel_unavailable", detail=f"{type(error).__name__}: {error}")
            self.panel = None

    def show(self, screen) -> None:
        if self.panel is None:
            return
        try:
            from medikiosk.edge.display import render

            self.panel.show(render(screen, self.scale))
        except Exception as error:
            self._emit("panel_failed", detail=f"{type(error).__name__}: {error}")
            self.panel = None  # stop trying; the interview carries on without a screen

    def close(self) -> None:
        if self.panel is not None:
            self.panel.close()
            self.panel = None


class MicrophoneStream:
    """Frames of raw 16 kHz mono PCM from a PulseAudio source."""

    def __init__(self, source: str) -> None:
        self.command = [
            "parecord",
            f"--device={source}",
            "--raw",
            "--format=s16le",
            f"--rate={SAMPLE_RATE}",
            "--channels=1",
            f"--latency-msec={FRAME_BYTES // 32}",
        ]
        self.process: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> MicrophoneStream:
        self.process = subprocess.Popen(
            self.command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        return self

    def __exit__(self, *_: object) -> None:
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def frame(self) -> bytes:
        """Read exactly one VAD frame; raises when the capture device disappears."""

        assert self.process is not None and self.process.stdout is not None
        chunk = self.process.stdout.read(FRAME_BYTES)
        if not chunk or len(chunk) < FRAME_BYTES:
            raise RuntimeError("Microphone stream ended; check the PulseAudio source")
        return chunk


def rms(pcm: bytes) -> int:
    """Root-mean-square level of 16-bit PCM.

    Written out rather than using `audioop`, which was removed in Python 3.13: the kiosk runs
    3.10 but the tests also run on newer interpreters.
    """

    if not pcm:
        return 0
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    if not samples:
        return 0
    return int(math.sqrt(sum(sample * sample for sample in samples) / len(samples)))


def pcm_to_wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm)
    return buffer.getvalue()


class JetsonVoiceRuntime:
    def __init__(
        self,
        settings: Settings,
        speech: WhisperCppSTT,
        voices: VoiceBank,
        vad: SileroVAD,
        session: ClinicalSession,
        store: EncryptedSessionStore | None = None,
        session_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.speech = speech
        self.voices = voices
        self.vad = vad
        self.session = session
        self.store = store
        self.session_id = session_id or str(uuid.uuid4())
        self.language = profile(settings.edge_language).code
        self.language_locked = not settings.auto_detect_language
        self.languages_heard: list[str] = []
        self.mic: MicrophoneStream | None = None
        self.transcript_log: list[dict[str, str]] = []
        self.view = PanelView(
            settings.panel_enabled, self._emit, settings.panel_target, settings.panel_scale
        )

    def prompt(self, key: str) -> str:
        return prompt_text(key, self.language)

    def _emit(self, event: str, **fields: object) -> None:
        """Progress events on stderr; the intake report is the only thing on stdout."""

        line = json.dumps({"event": event, **fields}, ensure_ascii=False)
        print(line, file=sys.stderr, flush=True)

    # ---------------------------------------------------------------- audio

    def _segmenter(self, *, barge_in: bool) -> SpeechSegmenter:
        if barge_in:
            # Residual echo survives AEC, so interrupting needs stronger, longer evidence.
            return SpeechSegmenter(
                threshold=self.settings.barge_in_threshold,
                start_ms=self.settings.barge_in_start_ms,
                silence_ms=self.settings.vad_silence_ms,
                max_utterance_s=self.settings.max_utterance_s,
            )
        return SpeechSegmenter(
            threshold=self.settings.vad_threshold,
            start_ms=self.settings.vad_start_ms,
            silence_ms=self.settings.vad_silence_ms,
            max_utterance_s=self.settings.max_utterance_s,
        )

    def speak(self, text: str, language: str | None = None) -> bytes | None:
        """Play a prompt. Returns the interrupting utterance if the patient barged in."""

        assert self.mic is not None
        started = time.monotonic()
        audio = self.voices.synthesize(text, language or self.language)
        self._emit("speaking", text=text, tts_ms=round((time.monotonic() - started) * 1000))
        with wave.open(io.BytesIO(audio)) as handle:
            pcm = handle.readframes(handle.getnframes())
            rate = handle.getframerate()
            channels = handle.getnchannels()
        player = subprocess.Popen(
            [
                "paplay",
                f"--device={self.settings.speaker_sink}",
                "--raw",
                "--format=s16le",
                f"--rate={rate}",
                f"--channels={channels}",
            ],
            stdin=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        writer = _AudioWriter(player, pcm, rate * channels)
        writer.start()

        self.vad.reset()
        playback_started = time.monotonic()
        segmenter = self._segmenter(barge_in=True)
        interruption: bytes | None = None
        stopped = False
        guard = self.settings.barge_in_guard_ms / 1000
        # Barge-in must mean "the patient started talking over the prompt", not "the room was
        # already talking". Arm only after the guard window AND after hearing one quiet frame.
        armed = False
        try:
            while player.poll() is None:
                frame = self.mic.frame()
                probability = self.vad.probability(frame)
                if not armed:
                    quiet = probability < self.settings.vad_threshold
                    if quiet and time.monotonic() - playback_started >= guard:
                        armed = True
                    continue
                utterance = segmenter.feed(probability, frame)
                if segmenter.triggered and not stopped:
                    # Barge-in: stop talking the moment speech is confirmed.
                    player.terminate()
                    stopped = True
                    self._emit(
                        "playback_stopped",
                        after_ms=round((time.monotonic() - playback_started) * 1000),
                    )
                if utterance is not None:
                    interruption = utterance
                    break
        finally:
            writer.stop()
            if player.poll() is None:
                player.terminate()
            try:
                player.wait(timeout=2)
            except subprocess.TimeoutExpired:
                player.kill()

        if interruption is not None:
            self._emit("barge_in", stop_ms=round((time.monotonic() - started) * 1000))
        elif segmenter.triggered:
            # Speech started but the prompt ended first; finish capturing that turn.
            interruption = self.listen(resume=segmenter)
        return interruption

    def listen(self, resume: SpeechSegmenter | None = None) -> bytes | None:
        assert self.mic is not None
        segmenter = resume or self._segmenter(barge_in=False)
        if resume is None:
            self.vad.reset()
        self._emit("listening", resumed=resume is not None)
        deadline = time.monotonic() + self.settings.turn_timeout_s
        while time.monotonic() < deadline:
            frame = self.mic.frame()
            utterance = segmenter.feed(self.vad.probability(frame), frame)
            if utterance is not None:
                return utterance
        return None

    # -------------------------------------------------------------- intake

    def transcribe(self, pcm: bytes) -> tuple[str, int]:
        """Transcribe a turn and, when enabled, follow the language the patient actually used."""

        # An ASR model asked to transcribe silence will invent a plausible sentence, and it
        # reports high confidence while doing it. Energy is the only trustworthy signal that
        # nobody spoke, and a fabricated answer here becomes a clinical fact.
        level = rms(pcm)
        if level < self.settings.min_utterance_rms:
            self._emit("silent_turn", rms=level, floor=self.settings.min_utterance_rms)
            return "", 0

        started = time.monotonic()
        # Detection runs on the opening turn only. Later turns are short - a bare "yes" carries
        # almost no language evidence - so re-detecting every turn would let one word throw the
        # session into another language mid-interview.
        pinned = None if not self.language_locked else self.language
        text, detected = self.speech.transcribe(pcm_to_wav(pcm), pinned)
        elapsed = round((time.monotonic() - started) * 1000)

        if detected:
            self.languages_heard.append(detected)
        follow = (
            not self.language_locked
            and bool(text)
            and detected is not None
            and detected != self.language
            and detected in LANGUAGES
        )
        if follow and self.voices.available(detected):
            self._emit("language", switched_from=self.language, switched_to=detected)
            self.language = detected
        elif follow:
            # Heard but not speakable: staying put beats answering in a language the kiosk has no
            # voice for.
            self._emit("language_unavailable", detected=detected)
        return text, elapsed

    def run_intake(self) -> dict:
        if not self.speech.health():
            raise RuntimeError(
                f"whisper.cpp server unreachable at {self.settings.whisper_url}; "
                "start it before intake"
            )
        missing = self.voices.missing([self.language, *self.settings.greeting_languages])
        if missing:
            raise RuntimeError(f"No installed voice for: {', '.join(sorted(set(missing)))}")

        with MicrophoneStream(self.settings.mic_source) as mic:
            self.mic = mic
            result = None
            silent_turns = 0
            attempts: dict[str, int] = {}
            unresolved: list[str] = []

            # Audio is always bound to the question it answers. Carrying it across a question
            # boundary made a barge-in answer land on the next question and rewrite the complaint.
            carry_question: str | None = None
            # Greet in more than one language so a patient knows they may answer in their own.
            carry_audio = None
            for code in self.settings.greeting_languages:
                if not self.voices.available(code):
                    continue
                self.view.show(prompt_screen("greeting", code))
                carry_audio = self.speak(prompt_text("greeting", code), language=code)
                if carry_audio is not None:
                    break  # they started answering; stop greeting and listen

            while True:
                question = self.session.state_machine.next_question(self.session.state, unresolved)
                if question is None:
                    break

                attempts[question.id] = attempts.get(question.id, 0) + 1
                if attempts[question.id] > self.settings.max_question_attempts:
                    # Leave the field unanswered rather than looping; the doctor sees the gap.
                    unresolved.append(question.id)
                    self._emit("unresolved", question=question.id)
                    carry_audio = carry_question = None
                    continue

                if carry_audio is not None and carry_question in (None, question.id):
                    captured, carry_audio, carry_question = carry_audio, None, None
                else:
                    carry_audio = carry_question = None
                    prompt = QUESTIONS[question.id].template_for(self.language)
                    self.view.show(
                        question_screen(question.id, self.language, step=(len(attempts), 7))
                    )
                    captured = self.speak(prompt) or self.listen()

                if captured is None:
                    silent_turns += 1
                    if silent_turns >= self.settings.max_unanswered_turns:
                        break
                    continue

                silent_turns = 0
                transcript, asr_ms = self.transcribe(captured)
                self._emit(
                    "transcript",
                    question=question.id,
                    text=transcript,
                    audio_ms=round(len(captured) / 32),
                    asr_ms=asr_ms,
                )

                if not transcript:
                    # Speaking over the retry prompt still answers the same question.
                    self.view.show(prompt_screen("repeat", self.language))
                    carry_audio = self.speak(self.prompt("repeat"))
                    carry_question = question.id
                    continue

                self.transcript_log.append({"question": question.id, "transcript": transcript})
                result = asyncio.run(
                    self.session.process_transcript(
                        transcript,
                        self.language,
                        asked=question,
                    )
                )
                self._persist()

                # Lock the language only once a turn has actually answered its question. Locking
                # on any non-empty transcript let one hallucinated English word pin the session to
                # English, after which every Hindi answer was force-decoded into invented English.
                answered = getattr(self.session.state, question.target_field) is not None
                if not self.language_locked and answered:
                    self.language_locked = True
                    self._emit("language_locked", language=self.language)

                if result.should_alert_staff:
                    self._emit("red_flag", rules=[flag.rule_id for flag in result.red_flags])
                    self.view.show(alert_screen(self.language))
                    self.speak(self.prompt("emergency"))
                    return self._report(result, alerted=True, unresolved=unresolved)

            self.view.show(prompt_screen("closing", self.language))
            self.speak(self.prompt("closing"))
            self.view.close()
            return self._report(result, alerted=False, unresolved=unresolved)

    def _persist(self) -> None:
        if self.store is not None:
            self.store.save(self.session_id, self.session.state)

    def _report(self, result, alerted: bool, unresolved: list[str] | None = None) -> dict:
        state = self.session.state
        flags = result.red_flags if result else []
        return {
            "session_id": self.session_id,
            "language": self.language,
            "languages_heard": sorted(set(self.languages_heard)),
            "staff_alerted": alerted,
            "red_flags": [flag.model_dump(mode="json") for flag in flags],
            "state": state.model_dump(mode="json"),
            "turns": self.transcript_log,
            "unresolved_questions": unresolved or [],
            "persisted": self.store is not None,
        }


class _AudioWriter:
    """Feeds PCM to paplay in a thread so barge-in can kill playback mid-prompt."""

    def __init__(self, player: subprocess.Popen[bytes], pcm: bytes, frames_per_second: int) -> None:
        self.pcm = pcm
        self.rate = frames_per_second
        self.player = player
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        assert self.player.stdin is not None
        chunk = self.rate // 10 * 2  # 100 ms
        try:
            for offset in range(0, len(self.pcm), chunk):
                if self._stop.is_set() or self.player.poll() is not None:
                    break
                self.player.stdin.write(self.pcm[offset : offset + chunk])
                self.player.stdin.flush()
            if not self._stop.is_set() and self.player.poll() is None:
                self.player.stdin.close()
        except (BrokenPipeError, ValueError, OSError):
            pass


def wait_for_touch(pin: int) -> None:
    """Block until the TTP223 pad is touched. Falls back to Enter when GPIO is unavailable."""

    try:
        import Jetson.GPIO as GPIO
    except ImportError:
        input("Press Enter to start intake: ")
        return

    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(pin, GPIO.IN)
    try:
        print(f"Waiting for touch on BOARD pin {pin} ...", flush=True)
        GPIO.wait_for_edge(pin, GPIO.RISING)
    finally:
        GPIO.cleanup(pin)


def build_runtime(settings: Settings) -> JetsonVoiceRuntime:
    llm = None
    if settings.clinical_llm_enabled:
        candidate = LocalLLMClinicalExtractor(settings.clinical_llm_model, settings.ollama_url)
        # Checked once here, not per-turn: this runtime is one long-lived process per kiosk
        # session, unlike the web server's one-extractor-per-connection setup.
        llm = candidate if candidate.health() else None
    return JetsonVoiceRuntime(
        settings=settings,
        speech=WhisperCppSTT(settings.whisper_url),
        voices=VoiceBank(
            settings.piper_binary,
            settings.voice_dir,
            settings.flite_binary,
            settings.flite_voice_dir,
            settings.prerendered_audio_dir,
        ),
        vad=SileroVAD(settings.silero_model_path),
        session=ClinicalSession(
            extractor=HybridClinicalExtractor(HeuristicClinicalExtractor(), llm),
            naturalizer=TemplateQuestionNaturalizer(),
        ),
        store=(
            EncryptedSessionStore(settings.session_store_path, settings.session_encryption_key)
            if settings.session_encryption_key
            else None
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Jetson intake loop")
    parser.add_argument("--touch-pin", type=int, default=None, help="TTP223 BOARD pin to start on")
    parser.add_argument("--report", type=Path, default=None, help="Write the intake report JSON")
    parser.add_argument("--loop", action="store_true", help="Serve patients continuously")
    parser.add_argument("--panel", action="store_true", help="Mirror the conversation on the LCD")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.panel:
        settings = settings.model_copy(update={"panel_enabled": True})
    while True:
        if args.touch_pin is not None:
            wait_for_touch(args.touch_pin)
        report = build_runtime(settings).run_intake()
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.report:
            args.report.write_text(rendered, encoding="utf-8")
        print(rendered)
        if not args.loop:
            return 0


if __name__ == "__main__":
    sys.exit(main())
