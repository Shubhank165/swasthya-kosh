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

    # --- timeline ------------------------------------------------------------
    #: `none`, `mock` or `vertex`. **`none` is the default and is not a
    #: placeholder.** With no provider the report still carries a dated,
    #: ordered history built by pure code; a provider only ever narrows that set
    #: to what relates to today's complaint. Turning one on is a decision about
    #: sending prior consultation content to a model — see
    #: `timeline_share_prior_records` below — not a performance tuning knob.
    timeline_provider: str = "none"
    timeline_model_id: str | None = None
    #: How many prior intakes are walked. Bounds both the cost of a model call
    #: and the amount of history that could leave the building.
    timeline_max_prior_intakes: int = 5
    #: Hard cap on rendered events, applied after validation, so a chatty model
    #: cannot lengthen a physician's report.
    timeline_max_events: int = 12
    #: Below this, a model-selected event is dropped.
    timeline_min_relevance: float = 0.3
    #: Scenario-keyed fixtures for the mock provider. Keyed by name rather than
    #: by a digest of the request: a digest-keyed fixture invalidates on any
    #: serialisation change, and the failure reads as "the mock broke".
    timeline_fixtures_dir: Path = BACKEND_ROOT / "tests" / "fixtures" / "timeline"
    #: **Defaults false, deliberately.** True is what lets prior consultation
    #: content — coded values, the patient's own words, prior medicine names —
    #: reach the model. That is a materially larger category of egress than the
    #: document images already sent, and it should not start happening because
    #: nobody set a variable. With it false the provider still runs, seeing only
    #: this intake's own documents and today's answers, which is strictly less
    #: than the OCR path already sends.
    timeline_share_prior_records: bool = False

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
    #: Invented people, for the demo. Mirrors `ocr_fixtures_dir`: a directory of
    #: fixtures the mock provider reads, so "who is behind this ABHA address"
    #: can be answered without an ABDM call. Every entry declares itself
    #: synthetic — see the README beside the file.
    abha_fixtures_dir: Path = BACKEND_ROOT / "app" / "adapters" / "abha" / "fixtures"

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

    # --- patient app ---------------------------------------------------------
    #: Server-side pepper for patient phone references. Without it a stored
    #: reference is a plain digest of a ten-digit number, which is reversible by
    #: exhaustive search in seconds — so this is not optional in any environment
    #: holding real patients, and `/readyz` reports it missing.
    patient_ref_pepper: str | None = None
    #: `mock` or `sms`. The mock returns the code in the response body in
    #: non-production environments and never sends anything.
    otp_provider: str = "mock"
    otp_ttl_seconds: int = 300
    #: Wrong-code attempts before the challenge is burned. Low, because a
    #: six-digit code with unlimited attempts is a four-hour brute force.
    otp_max_attempts: int = 5
    #: Challenges per phone per hour. Rate limiting an OTP endpoint is what
    #: stops it being used as a free SMS cannon aimed at a stranger.
    otp_max_per_hour: int = 5
    patient_session_ttl_hours: int = 720

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

    @field_validator("otp_provider")
    @classmethod
    def _validate_otp_provider(cls, value: str) -> str:
        allowed = {"mock", "sms"}
        if value not in allowed:
            raise ValueError(f"otp_provider must be one of {sorted(allowed)}")
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

    #: The question content version this deployment serves. The Jetson, the
    #: patient app and this backend must agree on it: it is stamped into every
    #: record's provenance, so "which questions produced this answer" is
    #: answerable months later.
    content_version: str = "questions-2026-09-01"
    #: Languages the question bundle advertises. Distinct from
    #: `report_languages`: a prompt and a report line are different artefacts,
    #: reviewed separately, and a language may have one without the other.
    #: The loader refuses to start if any question lacks a prompt in one of
    #: these, so adding a language here is a commitment to translate.
    question_languages: list[str] = Field(default_factory=lambda: ["en", "hi"])

    @property
    def questions_dir(self) -> Path:
        return self.clinical_content_dir / "questions"

    @property
    def questioning_dir(self) -> Path:
        """The questioning engine's content — slots, questions, red flags.

        Separate from `questions_dir`, which holds the hand-authored bundle the
        engine replaces. Both are on disk while the old one still has readers.
        """
        return self.clinical_content_dir / "questioning"

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
