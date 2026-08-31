"""FastAPI application.

Startup loads and validates the clinical content. That validation is strict on
purpose: a pathway that does not parse, or a red-flag rule that reads a concept
nobody asks, stops the process. A system that quietly asks fewer safety
questions than it was configured to is the failure mode worth refusing to boot
over.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1 import consent, intakes, queues, realtime, terminology
from app.core.config import get_settings
from app.core.content import get_clinical_content
from app.core.errors import MediKioskError
from app.core.logging import configure_logging, get_logger
from app.events.bus import get_event_bus
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
        pathway_id=",".join(content.pathways.ids()),
    )
    pending = content.review_queue()
    if pending:
        # Not fatal — the content is usable — but it must be visible, because it
        # is the agenda for the next clinician review session.
        logger.warning("clinical_review_pending", count=len(pending))

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
        version="0.1.0",
        description=(
            "Pre-consultation clinical intake for AYUSH OPDs. "
            "This service produces a draft intake requiring physician verification. "
            "It states no diagnosis and gives no medical advice."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    @app.exception_handler(MediKioskError)
    async def _handle_domain_error(_: Request, exc: MediKioskError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, object]:
        content = get_clinical_content()
        return {
            "status": "ok",
            "environment": settings.environment,
            "queue_mode": settings.queue_mode,
            "pathways": len(content.pathways),
            "red_flag_rules": len(content.red_flags),
            "concepts": len(content.concepts),
            "clinical_review_pending": len(content.review_queue()),
        }

    prefix = settings.api_prefix
    app.include_router(intakes.router, prefix=prefix)
    app.include_router(intakes.physician_router, prefix=prefix)
    app.include_router(intakes.alerts_router, prefix=prefix)
    app.include_router(consent.router, prefix=prefix)
    app.include_router(queues.departments_router, prefix=prefix)
    app.include_router(queues.router, prefix=prefix)
    app.include_router(queues.tickets_router, prefix=prefix)
    app.include_router(queues.instances_router, prefix=prefix)
    app.include_router(terminology.router, prefix=prefix)
    app.include_router(realtime.router)
    return app


app = create_app()
