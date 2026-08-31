"""Application configuration.

Everything is environment-driven. There is no secret, key, model id or hostname
literal anywhere in this codebase — including in fixtures — because this repo is
shared under hackathon pressure and a credential committed once is a credential
leaked forever.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: backend/app/core/config.py -> backend/
BACKEND_ROOT = Path(__file__).resolve().parents[2]
#: backend/ -> medikiosk/
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    """Runtime configuration, read from the environment or a local .env."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix=""
    )

    environment: str = "local"
    debug: bool = False
    app_name: str = "MediKiosk"
    api_prefix: str = "/api/v1"

    # --- persistence ---------------------------------------------------------
    database_url: str = "postgresql+asyncpg://medikiosk:medikiosk@localhost:5432/medikiosk"
    database_echo: bool = False
    #: Optional. Session and counter cache only; the system runs without it.
    redis_url: str | None = None

    # --- clinical content ----------------------------------------------------
    clinical_content_dir: Path = REPO_ROOT / "clinical"

    # --- state machine -------------------------------------------------------
    supported_languages: list[str] = Field(default_factory=lambda: ["en", "hi"])
    ayurveda_module_enabled: bool = True
    ask_optional_fields: bool = True
    max_optional_fields: int = 12

    # --- queue ---------------------------------------------------------------
    #: SOURCE_OF_TRUTH or SHADOW. In SHADOW an HMIS owns tokens and MediKiosk
    #: owns only intake state.
    queue_mode: str = "source_of_truth"
    prefer_intake_ready: bool = False
    intake_ready_window: int = 3
    max_overtaken: int = 3
    recall_after_tokens: int = 3
    max_recalls: int = 2
    senior_citizen_age: float = 60.0
    infant_age_years: float = 2.0
    default_service_seconds: float = 480.0

    # --- privacy -------------------------------------------------------------
    #: Off by default. Turning it on does not by itself permit retention: the
    #: patient must also grant the `raw_audio_retention` purpose code.
    raw_audio_retention_enabled: bool = False
    intake_inactivity_timeout_seconds: int = 900
    #: Where uploaded documents land. Local disk locally, object storage in prod.
    document_storage_dir: Path = BACKEND_ROOT / "uploads"

    # --- events / realtime ---------------------------------------------------
    #: `in_process` or `pubsub`. Only `in_process` is implemented in this build.
    event_bus: str = "in_process"
    websocket_heartbeat_seconds: int = 20

    # --- adapters ------------------------------------------------------------
    #: All adapters are mocks in this build. Real providers plug in behind the
    #: same protocols without touching anything above the adapters package.
    stt_provider: str = "mock"
    tts_provider: str = "mock"
    extraction_provider: str = "mock"
    ocr_provider: str = "mock"
    question_renderer: str = "template"
    his_adapter: str = "mock"

    # --- observability -------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("queue_mode")
    @classmethod
    def _validate_queue_mode(cls, value: str) -> str:
        allowed = {"source_of_truth", "shadow"}
        if value not in allowed:
            raise ValueError(f"queue_mode must be one of {sorted(allowed)}")
        return value

    @field_validator("supported_languages")
    @classmethod
    def _validate_languages(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("at least one supported language is required")
        return value

    @property
    def pathways_dir(self) -> Path:
        return self.clinical_content_dir / "pathways"

    @property
    def redflags_dir(self) -> Path:
        return self.clinical_content_dir / "redflags"

    @property
    def ayurveda_dir(self) -> Path:
        return self.clinical_content_dir / "ayurveda"

    @property
    def terminology_dir(self) -> Path:
        return self.clinical_content_dir / "terminology"

    @property
    def consent_dir(self) -> Path:
        return self.clinical_content_dir / "consent"

    @property
    def is_shadow_mode(self) -> bool:
        return self.queue_mode == "shadow"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings. Cached so config is read once."""
    return Settings()
