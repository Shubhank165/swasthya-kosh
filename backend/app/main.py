"""FastAPI application.

Startup loads and validates the clinical content and selects the providers, and
both are strict on purpose. A report template missing a string renders a blank
heading, an interaction row missing its source becomes an unattributable safety
claim, and neither shows up until a clinician is reading the output. Failing to
boot is the loud version of a failure that is otherwise silent.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.deps import get_providers
from app.api.v1 import (
    consent,
    content,
    documents,
    fhir,
    hospitals,
    intakes,
    kiosk,
    patient_auth,
    patients,
    realtime,
    terminology,
    worker,
)
from app.api.v1 import worklist as worklist_api
from app.core.config import get_settings
from app.core.content import get_clinical_content
from app.core.errors import MediKioskError
from app.core.logging import configure_logging, get_logger
from app.db import get_engine
from app.events.bus import get_event_bus
from app.normalize.registry import supported_versions
from app.realtime.hub import get_hub

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    content = get_clinical_content()
    logger.info(
        "clinical_content_loaded",
        count=len(content.concepts),
        language=",".join(content.templates.languages),
    )
    pending = content.review_queue()
    if pending:
        # Not fatal — the content is usable — but it must be visible, because it
        # is the agenda for the next clinician review session.
        logger.warning("clinical_review_pending", count=len(pending))

    providers = get_providers(settings)
    logger.info("providers_ready", **providers.describe())
    if settings.demo_mode:
        logger.warning("demo_mode_enabled")
    if settings.uses_cloud_models and not settings.vertex_zdr_enabled:
        # Reachable only if a provider was constructed some other way; the
        # adapters refuse this themselves. Logged anyway — the cost of being
        # wrong here is a patient's prescription leaving the country.
        logger.error("cloud_models_without_zdr")

    # Bridge the event bus onto the WebSocket hub so every published event fans
    # out to connected dashboards without any router knowing the hub exists.
    bus = await get_event_bus()
    hub = get_hub()
    bus.subscribe(hub.broadcast)

    yield

    from app.db import dispose

    await dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} — clinical intake backend",
        version="0.2.0",
        description=(
            "Receives completed intakes from the MediKiosk device, reads uploaded "
            "documents, and assembles the physician report. "
            "This service produces a draft requiring physician verification. "
            "It states no diagnosis and gives no medical advice. "
            "It does not conduct the interview and does not evaluate red-flag rules; "
            "both happen on the device."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    @app.exception_handler(MediKioskError)
    async def _handle_domain_error(_: Request, exc: MediKioskError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, Any]:
        """Liveness. Answers as long as the process is running.

        Deliberately touches nothing: a liveness probe that queries the database
        restarts a healthy container every time the database hiccups.
        """
        return {"status": "ok", "service": settings.app_name}

    @app.get("/readyz", tags=["ops"])
    async def readyz() -> JSONResponse:
        """Readiness. Content loaded, providers built, database reachable.

        Also reports which providers are live, so "what is this deployment
        actually running" is one curl rather than a guess.
        """
        checks: dict[str, Any] = {}
        ready = True

        try:
            content = get_clinical_content()
            checks["content"] = {
                "concepts": len(content.concepts),
                "interactions": len(content.interactions),
                "languages": list(content.templates.languages),
            }
        except Exception as exc:
            ready = False
            checks["content"] = {"error": type(exc).__name__}

        try:
            checks["providers"] = get_providers(settings).describe()
        except Exception as exc:
            ready = False
            checks["providers"] = {"error": type(exc).__name__}

        try:
            from sqlalchemy import text

            async with get_engine().connect() as connection:
                await connection.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            ready = False
            checks["database"] = {"error": type(exc).__name__}

        # Which deployment shape this is. Two Cloud Run services run this same
        # image and differ only in environment, so "am I looking at the API or
        # the worker" has to be answerable without reading the deploy script.
        checks["dispatch"] = {
            "document_queue": settings.document_queue,
            "worker_route": settings.pubsub_push_enabled,
        }

        body = {
            "status": "ready" if ready else "not_ready",
            "environment": settings.environment,
            "demo": settings.demo_mode,
            "schema_versions": list(supported_versions()),
            "checks": checks,
        }
        return JSONResponse(status_code=200 if ready else 503, content=body)

    prefix = settings.api_prefix
    # Open routes first, and grouped, so "what can be reached without a
    # credential" is one place in this file rather than a property you work out
    # by reading every router.
    app.include_router(content.router, prefix=prefix)
    app.include_router(hospitals.router, prefix=prefix)
    app.include_router(patient_auth.router, prefix=prefix)

    app.include_router(kiosk.router, prefix=prefix)
    app.include_router(intakes.router, prefix=prefix)
    app.include_router(documents.router, prefix=prefix)
    app.include_router(documents.content_router, prefix=prefix)
    app.include_router(patients.router, prefix=prefix)
    app.include_router(worklist_api.router, prefix=prefix)
    app.include_router(consent.router, prefix=prefix)
    app.include_router(fhir.router, prefix=prefix)
    app.include_router(terminology.router, prefix=prefix)
    if settings.pubsub_push_enabled:
        # Registered only on the worker deployment. See `api/v1/worker.py`.
        app.include_router(worker.router, prefix=prefix)
    app.include_router(realtime.router)
    return app


app = create_app()
