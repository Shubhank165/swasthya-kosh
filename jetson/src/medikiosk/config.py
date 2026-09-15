from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deployment_profile: Literal["online", "pi", "jetson", "demo"] = "online"
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model: str = "gpt-5.6-terra"
    sarvam_api_key: str | None = Field(default=None, repr=False)
    sarvam_stt_language: str = "auto"
    sarvam_tts_language: str = "hi-IN"
    sarvam_tts_speaker: str = "shubh"
    session_store_path: Path = Path("data/medikiosk.db")
    session_encryption_key: str | None = Field(default=None, repr=False)
    staff_users_path: Path | None = None
    staff_allow_insecure_http: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)

    # Offline edge runtime. Devices are the PulseAudio echo-cancelled endpoints created by
    # scripts/setup_jetson_audio.sh; the VAD numbers are room-dependent calibration knobs.
    whisper_url: str = "http://127.0.0.1:11500"
    # Hindi goes to IndicConformer (scripts/indic_asr_server.py); measured 2x lower CER and
    # 3.7x faster than whisper on this board. Everything else stays on whisper.
    indic_asr_url: str = "http://127.0.0.1:11600"
    bhashini_url: str = "http://127.0.0.1:11400"
    edge_language: str = "hi"
    # Whisper reports the language it heard, so the kiosk can follow the patient instead of making
    # them pick from a list. Turn this off to pin a single language.
    auto_detect_language: bool = True
    # Spoken at session start so a patient knows they may answer in their own language.
    greeting_languages: tuple[str, ...] = ("hi", "en")
    piper_binary: Path = Path("offline/jetson/bin/piper/piper")
    voice_dir: Path = Path("offline/jetson/models")
    # Prompts rendered ahead of time by scripts/prerender_prompts.py. Missing directory
    # just means every prompt is synthesized live, which is the old behaviour.
    prerendered_audio_dir: Path = Path("offline/audio")
    flite_binary: Path = Path("/home/ubuntu/bhashini_models/tts/flite/bin/flite")
    flite_voice_dir: Path = Path("/home/ubuntu/bhashini_models/tts/flite/voices")
    mic_source: str = "medikiosk_mic"
    speaker_sink: str = "medikiosk_speaker"
    silero_model_path: Path = Path("offline/jetson/models/silero_vad.onnx")
    vad_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    vad_start_ms: int = Field(default=160, ge=32)
    vad_silence_ms: int = Field(default=700, ge=100)
    barge_in_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    barge_in_start_ms: int = Field(default=224, ge=32)
    # A prompt cannot be interrupted during this opening window, and speech already under way
    # when the prompt begins is not an interruption at all. Without both, background conversation
    # in the room barged the kiosk out of every prompt 7 ms in and was recorded as the answer.
    barge_in_guard_ms: int = Field(default=600, ge=0)
    max_utterance_s: float = Field(default=15.0, gt=0)
    turn_timeout_s: float = Field(default=20.0, gt=0)
    # Privacy timeout: an abandoned encounter is warned, then cleared for the next patient.
    idle_timeout_s: float = Field(default=600.0, gt=0)
    max_unanswered_turns: int = Field(default=3, ge=1)
    max_question_attempts: int = Field(default=2, ge=1)
    # Whisper invents fluent speech from silence - on digital silence it returned " you" with
    # no_speech_prob 2e-10 - so near-silent turns are rejected on energy before they reach ASR.
    min_utterance_rms: int = Field(default=120, ge=0)
    # The 2.8" panel is opt-in: opening SPI on a machine without one would fail, and the intake
    # must run headless. A panel fault never stops an interview.
    panel_enabled: bool = False
    # "spi" drives the 2.8 inch panel; "tablet" serves the same rendered screens to a tablet
    # browser held fullscreen over the USB link. Scale multiplies the 320x240 layout so a 10 inch
    # tablet gets a real render rather than an upscaled thumbnail.
    panel_target: Literal["spi", "tablet"] = "spi"
    panel_scale: int = Field(default=4, ge=1, le=8)
    panel_port: int = Field(default=8800, ge=1, le=65535)
    # Heuristic extractor only recognizes hardcoded phrases ("chest pain"). The local LLM fills
    # in anything else the patient says (headache, ankle, sugar) - health-checked at session start
    # so a stopped/missing Ollama falls back to heuristic-only instead of breaking the demo.
    # The adaptive questioning agent picks each question from what is still unknown instead of
    # walking ClinicalStateMachine's fixed ten. Off by default: it changes the shape of every
    # interview, and the fixed plan is the one that has been demoed. Red-flag evaluation is
    # unaffected either way - see clinical/adaptive.py.
    adaptive_questioning: bool = False
    questioning_content_dir: Path = Path("clinical/questioning")
    clinical_llm_enabled: bool = True
    clinical_llm_model: str = "gemma3:1b"
    ollama_url: str = "http://127.0.0.1:11434"
    # Handwritten documents. PP-OCRv5 reads printed Devanagari well and handwriting badly, so a
    # page the confidence tail marks as handwritten (kiosk/handwriting.py) can be sent to the
    # hospital intake API, whose reader - Gemini on Vertex, asia-south1 - handles handwriting.
    # Off by default for two reasons that are policy rather than code: it needs internet, which
    # breaks the offline guarantee the rest of the kiosk makes, and the image leaves the building.
    # Turn it on deliberately, not by accident.
    handwritten_cloud_ocr: bool = False
    intake_api_url: str = "https://medikiosk-api-tjynzes4vq-el.a.run.app"
    # A file rather than an environment variable: an env var is readable by anything that can see
    # the process and turns up in crash dumps and `ps e`. Mode 0600, outside the kiosk tree.
    intake_token_path: Path = Path("~/.config/medikiosk/kiosk_token")
    # Which device an exported record came from. Defaults to the hostname, which is already
    # unique per Jetson; set it explicitly when an OPD runs more than one and the hostnames
    # do not say which desk is which.
    kiosk_id: str | None = None
    # Fonts for the PDF slip. Missing files fall back to Pillow's default (Latin only).
    slip_font_devanagari: Path = Path(
        "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf"
    )
    slip_font_latin: Path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

    @property
    def openai_configured(self) -> bool:
        return self.deployment_profile == "online" and bool(self.openai_api_key)

    @property
    def sarvam_configured(self) -> bool:
        return self.deployment_profile == "online" and bool(self.sarvam_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
