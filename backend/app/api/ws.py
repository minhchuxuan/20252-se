"""WebSocket live feed (REQ-4.1.1 push updates, SRS 3.4 WSS).

Bridges the in-process event bus to connected clients: telemetry readings and
notifications for a home are pushed in real time, so the dashboard updates
without polling. The ConnectionManager is itself an Observer of the bus.
"""
from __future__ import annotations

import logging

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.events import EventType, bus
from ..core.security import decode_access_token

logger = logging.getLogger("sheo.ws")
router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[tuple[WebSocket, int]] = []
        self._wired = False

    async def connect(self, ws: WebSocket, home_id: int) -> None:
        await ws.accept()
        self._connections.append((ws, home_id))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections = [(w, h) for (w, h) in self._connections if w is not ws]

    async def broadcast(self, home_id: int, message: dict) -> None:
        dead = []
        for w, h in self._connections:
            if h != home_id:
                continue
            try:
                await w.send_json(message)
            except Exception:
                dead.append(w)
        for w in dead:
            self.disconnect(w)

    def wire_bus(self) -> None:
        if self._wired:
            return

        async def on_telemetry(payload: dict) -> None:
            await self.broadcast(payload.get("home_id"), {"type": "telemetry", **payload})

        async def on_notification(payload: dict) -> None:
            await self.broadcast(payload.get("home_id"), {"type": "notification", **payload})

        bus.subscribe(EventType.TELEMETRY_READING, on_telemetry)
        bus.subscribe(EventType.NOTIFICATION_CREATED, on_notification)
        self._wired = True


manager = ConnectionManager()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, token: str = "") -> None:
    try:
        payload = decode_access_token(token)
        home_id = payload.get("home_id")
    except jwt.PyJWTError:
        await websocket.close(code=4401)
        return
    if home_id is None:
        await websocket.close(code=4401)
        return
    await manager.connect(websocket, home_id)
    try:
        while True:
            await websocket.receive_text()  # keepalive / client pings
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
