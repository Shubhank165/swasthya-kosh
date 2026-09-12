"""Provider selection.

The one place a config string becomes an implementation. Every provider is built
here and nowhere else, so "what is this deployment actually running" is a single
function call — which is what `/readyz` reports and what the demo banner is
derived from.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters.abha.providers import MockABHAProvider, SandboxABHAProvider, build_provider
from app.adapters.llm.mock import MockRepairProvider
from app.adapters.ocr.mock import MockOCRProvider
from app.adapters.otp.senders import MockOTPSender, SMSOTPSender, build_sender
from app.adapters.protocols import (
    ABHAProvider,
    ObjectStore,
    OCRProvider,
    OTPSender,
    RepairProvider,
    TimelineProvider,
)
from app.adapters.storage.stores import GCSObjectStore, LocalObjectStore, build_store
from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Providers:
    """Everything the services depend on from outside the process."""

    ocr: OCRProvider
    repair: RepairProvider | None
    abha: ABHAProvider
    storage: ObjectStore
    otp: OTPSender
    #: `None` when `TIMELINE_PROVIDER=none`, which is the default. The report
    #: still carries a full dated history — pure code builds it — so "disabled"
    #: here means no relevance filtering, not no timeline.
    timeline: TimelineProvider | None = None

    def describe(self) -> dict[str, str]:
        """What is live. Safe to serve from `/readyz`."""
        return {
            "ocr": self.ocr.name,
            "repair": self.repair.name if self.repair is not None else "disabled",
            "abha": self.abha.name,
            "storage": self.storage.name,
            "otp": self.otp.name,
            "timeline": self.timeline.name if self.timeline is not None else "disabled",
        }


def build_ocr(settings: Settings) -> OCRProvider:
    if settings.ocr_provider == "gemini":
        # Imported lazily: the module refuses to construct without residency and
        # ZDR configured, and a mock-only deployment should not need the SDK
        # installed to start.
        from app.adapters.ocr.gemini import GeminiOCRProvider

        return GeminiOCRProvider(settings)
    return MockOCRProvider(settings.ocr_fixtures_dir, demo=settings.demo_mode)


def build_repair(settings: Settings) -> RepairProvider | None:
    """The repair provider, or `None` when repair is switched off.

    `REPAIR_PROVIDER=none` is a supported configuration: a hospital that will
    not have a model touch patient input at all still gets ingest, documents and
    the report. Malformed payloads then go straight to `ingest_raw` and
    `needs_manual_review`, which is a worse outcome than repair but an honest
    one.
    """
    if settings.repair_provider == "none":
        return None
    if settings.repair_provider == "vertex":
        from app.adapters.llm.vertex import VertexRepairProvider

        return VertexRepairProvider(settings)
    return MockRepairProvider()


def build_timeline(settings: Settings) -> TimelineProvider | None:
    """The timeline provider, or `None` — and `None` is the default.

    Unlike every other provider here, "off" is not a degraded mode. With no
    provider the report carries the deterministic timeline: every dated entry on
    record, newest first, labelled as unfiltered. A provider only ever narrows
    that to what relates to today's complaint. So the decision to turn one on is
    a decision about sending records to a model, not about whether the feature
    works.
    """
    if settings.timeline_provider == "vertex":
        from app.adapters.timeline.vertex import VertexTimelineProvider

        return VertexTimelineProvider(settings)
    if settings.timeline_provider == "mock":
        from app.adapters.timeline.mock import MockTimelineProvider

        return MockTimelineProvider(settings.timeline_fixtures_dir)
    return None


def build_abha(settings: Settings) -> MockABHAProvider | SandboxABHAProvider:
    return build_provider(settings)


def build_storage(settings: Settings) -> LocalObjectStore | GCSObjectStore:
    return build_store(settings)


def build_otp(settings: Settings) -> MockOTPSender | SMSOTPSender:
    return build_sender(settings)


def build_providers(settings: Settings) -> Providers:
    """Everything, from config."""
    providers = Providers(
        ocr=build_ocr(settings),
        repair=build_repair(settings),
        abha=build_abha(settings),
        storage=build_storage(settings),
        otp=build_otp(settings),
        timeline=build_timeline(settings),
    )
    logger.info("providers_selected", **providers.describe())
    return providers
