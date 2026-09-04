"""Application configuration.

Everything is environment-driven. There is no secret, key, model id or hostname
literal anywhere in this codebase — including in fixtures — because this repo is
shared under hackathon pressure and a credential committed once is a credential
leaked forever.

Model ids in particular are config and never inline: `OCR_MODEL_ID` and
`REPAIR_MODEL_ID` are read here and nowhere else, so swapping a model is a
deployment change, not a code change.
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
    #: The facility's own timezone. Report dates are the hospital's calendar day,
    #: never the server's UTC day.
    facility_timezone: str = "Asia/Kolkata"

    # --- persistence ---------------------------------------------------------
    database_url: str = "postgresql+asyncpg://medikiosk:medikiosk@localhost:5432/medikiosk"
    database_echo: bool = False

    # --- clinical content ----------------------------------------------------
    clinical_content_dir: Path = REPO_ROOT / "clinical"
    #: Report language templates. Written once per language, never translated at
    #: runtime.
    report_languages: list[str] = Field(default_factory=lambda: ["en", "hi"])
    default_report_language: str = "en"

    # --- object storage ------------------------------------------------------
    #: `local` or `gcs`. Local disk for the laptop demo, GCS in the cloud.
    storage_backend: str = "local"
    document_storage_dir: Path = BACKEND_ROOT / "uploads"
    gcs_bucket: str | None = None
    #: Signed URLs are short-lived by policy. A document link that outlives the
    #: consultation is a document link that ends up in a WhatsApp group.
    signed_url_ttl_seconds: int = 300

    # --- OCR -----------------------------------------------------------------
    #: `mock` or `gemini`. Every test and the demo path run `mock`.
    ocr_provider: str = "mock"
    ocr_model_id: str | None = None
    #: Any numeric value in a dose or a lab result below this floor is marked
    #: `needs_verification` and rendered distinctly. The OCR benchmark read
    #: ९००.२ for १००.२; a wrong digit in a dose is the worst error this
    #: system can make.
    ocr_confidence_floor: float = 0.85
    #: Below this, the image is rejected outright and a reshoot is requested.
    ocr_quality_floor: float = 0.35
    ocr_fixtures_dir: Path = BACKEND_ROOT / "tests" / "fixtures" / "ocr"

    # --- repair (the one place a language model touches clinical input) ------
    #: `mock`, `vertex`, or `none` to disable repair entirely.
    repair_provider: str = "mock"
    repair_model_id: str | None = None
    repair_max_attempts: int = 1

    # --- Vertex --------------------------------------------------------------
    vertex_project: str | None = None
    vertex_region: str = "asia-south1"
    #: Must be true before any Vertex call is made in an environment holding real
    #: patient data. See docs/DECISIONS.md.
    vertex_zdr_enabled: bool = False

    # --- identity ------------------------------------------------------------
    #: `mock` or `sandbox`. The mock stamps `"source": "mock"` on every response
    #: and the API surfaces it — a mocked government integration is never
    #: presented as live.
    abha_provider: str = "mock"
    abdm_base_url: str | None = None

    # --- demo ----------------------------------------------------------------
    #: Serves cached OCR results for known fixture documents and marks every
    #: response `"demo": true`.
    demo_mode: bool = False

    # --- events / realtime ---------------------------------------------------
    #: Where a newly uploaded document's OCR work goes: `inline` runs it as a
    #: background task in this process, `pubsub` publishes identifiers to a
    #: topic and a separate Cloud Run worker does the reading. Both end at the
    #: same `DocumentService.process`.
    #:
    #: There is deliberately no equivalent switch for the event bus. Fan-out to
    #: dashboards is in-process only, because a second API instance would need a
    #: broker-backed bus that nothing here implements — and a setting that
    #: silently does nothing is worse than no setting.
    document_queue: str = "inline"
    #: The GCP project for Pub/Sub and Cloud Storage. Vertex has its own, so a
    #: deployment can keep model calls in one project and data in another.
    gcp_project: str | None = None
    pubsub_topic: str | None = None
    #: Registers the Pub/Sub push endpoint that drives OCR on Cloud Run. Off by
    #: default, and off on the public API service: the worker is a separate
    #: deployment of the same image, so the route exists only where it is meant
    #: to be reachable rather than being published and then guarded.
    pubsub_push_enabled: bool = False
    #: Shared secret the push subscription presents. Defence in depth behind
    #: Cloud Run's own IAM check; unset means the platform check is the only one.
    pubsub_push_token: str | None = None
    websocket_heartbeat_seconds: int = 20

    # --- auth ----------------------------------------------------------------
    #: Kiosk service tokens, `token: hospital_id`. Loaded from Secret Manager in
    #: the cloud; never committed.
    kiosk_tokens: dict[str, str] = Field(default_factory=dict)
    #: Header-based principals, for local development and the dashboard build.
    #: Off in any environment that holds real data.
    allow_header_auth: bool = True

    # --- observability -------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("storage_backend")
    @classmethod
    def _validate_storage_backend(cls, value: str) -> str:
        allowed = {"local", "gcs"}
        if value not in allowed:
            raise ValueError(f"storage_backend must be one of {sorted(allowed)}")
        return value

    @field_validator("ocr_provider")
    @classmethod
    def _validate_ocr_provider(cls, value: str) -> str:
        allowed = {"mock", "gemini"}
        if value not in allowed:
            raise ValueError(f"ocr_provider must be one of {sorted(allowed)}")
        return value

    @field_validator("repair_provider")
    @classmethod
    def _validate_repair_provider(cls, value: str) -> str:
        allowed = {"mock", "vertex", "none"}
        if value not in allowed:
            raise ValueError(f"repair_provider must be one of {sorted(allowed)}")
        return value

    @field_validator("document_queue")
    @classmethod
    def _validate_document_queue(cls, value: str) -> str:
        allowed = {"inline", "pubsub"}
        if value not in allowed:
            raise ValueError(f"document_queue must be one of {sorted(allowed)}")
        return value

    @field_validator("abha_provider")
    @classmethod
    def _validate_abha_provider(cls, value: str) -> str:
        allowed = {"mock", "sandbox"}
        if value not in allowed:
            raise ValueError(f"abha_provider must be one of {sorted(allowed)}")
        return value

    @field_validator("ocr_confidence_floor", "ocr_quality_floor")
    @classmethod
    def _validate_floor(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence floors must be within 0.0..1.0")
        return value

    @field_validator("report_languages")
    @classmethod
    def _validate_languages(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("at least one report language is required")
        return value

    @property
    def terminology_dir(self) -> Path:
        return self.clinical_content_dir / "terminology"

    @property
    def consent_dir(self) -> Path:
        return self.clinical_content_dir / "consent"

    @property
    def interactions_dir(self) -> Path:
        return self.clinical_content_dir / "interactions"

    @property
    def report_templates_dir(self) -> Path:
        return self.clinical_content_dir / "report_templates"

    @property
    def uses_cloud_models(self) -> bool:
        """True when any call would leave the building."""
        return self.ocr_provider == "gemini" or self.repair_provider == "vertex"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings. Cached so config is read once."""
    return Settings()
