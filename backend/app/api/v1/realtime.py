"""WebSocket endpoints.

`/ws/dashboard?department=` fans queue, intake and alert activity out to staff
screens. `/ws/intakes/{id}` gives the kiosk live state for the session it is
driving.

Neither carries clinical text: the frames are the `Event` wire form, and events
are identifiers and counters by construction.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.realtime.hub import DASHBOARD_EVENTS, INTAKE_EVENTS, get_hub

router = APIRouter(tags=["realtime"])


async def _heartbeat(socket: WebSocket, interval: int) -> None:
    """Keep the socket alive through a hospital NAT that times idle connections
    out. A waiting-room display that silently stops updating is worse than one
    that visibly disconnects."""
    while True:
        await asyncio.sleep(interval)
        await socket.send_json({"event": "heartbeat"})


@router.websocket("/ws/dashboard")
async def dashboard_socket(
    socket: WebSocket,
    department: Annotated[str | None, Query()] = None,
) -> None:
    hub = get_hub()
    settings = get_settings()
    subscription = await hub.connect(
        socket, names=DASHBOARD_EVENTS, department_code=department
    )
    heartbeat = asyncio.create_task(
        _heartbeat(socket, settings.websocket_heartbeat_seconds)
    )
    try:
        await socket.send_json(
            {"event": "subscribed", "channel": "dashboard", "department": department}
        )
        while True:
            # The dashboard is push-only; receiving is how we notice a hangup.
            await socket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat
        await hub.disconnect(subscription)


@router.websocket("/ws/intakes/{intake_id}")
async def intake_socket(socket: WebSocket, intake_id: str) -> None:
    hub = get_hub()
    settings = get_settings()
    subscription = await hub.connect(socket, names=INTAKE_EVENTS, intake_id=intake_id)
    heartbeat = asyncio.create_task(
        _heartbeat(socket, settings.websocket_heartbeat_seconds)
    )
    try:
        await socket.send_json(
            {"event": "subscribed", "channel": "intake", "intake_id": intake_id}
        )
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat
        await hub.disconnect(subscription)
