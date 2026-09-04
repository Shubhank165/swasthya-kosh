"""WebSocket endpoints.

`/ws/worklist?department=` fans intake, document and alert activity out to the
doctor dashboard. `/ws/intakes/{id}` lets the kiosk that submitted an intake see
its document being read while the patient is still standing there.

Neither carries clinical text: the frames are the `Event` wire form, and events
are identifiers and counters by construction.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.realtime.hub import INTAKE_EVENTS, WORKLIST_EVENTS, get_hub

router = APIRouter(tags=["realtime"])


async def _heartbeat(socket: WebSocket, interval: int) -> None:
    """Keep the socket alive through a hospital NAT that times idle connections
    out. A waiting-room display that silently stops updating is worse than one
    that visibly disconnects."""
    while True:
        await asyncio.sleep(interval)
        await socket.send_json({"event": "heartbeat"})


@router.websocket("/ws/worklist")
async def worklist_socket(
    socket: WebSocket,
    department: Annotated[str | None, Query()] = None,
) -> None:
    hub = get_hub()
    settings = get_settings()
    subscription = await hub.connect(
        socket, names=WORKLIST_EVENTS, department_code=department
    )
    heartbeat = asyncio.create_task(
        _heartbeat(socket, settings.websocket_heartbeat_seconds)
    )
    try:
        await socket.send_json(
            {"event": "subscribed", "channel": "worklist", "department": department}
        )
        while True:
            # The worklist is push-only; receiving is how we notice a hangup.
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
