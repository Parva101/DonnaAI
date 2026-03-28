"""Socket.IO server.

Mounted as an ASGI sub-app on FastAPI. Provides real-time event push to
the frontend dashboard (new messages, notifications, sync progress, etc.).

Usage in main.py:
    from app.core.socketio_server import sio_app
    app.mount("/ws", sio_app)
"""

from __future__ import annotations

from typing import Any

import socketio

from app.core.config import settings

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.cors_origins,
    logger=False,
    engineio_logger=False,
)

_inner_app = socketio.ASGIApp(sio, socketio_path="/socket.io")


class SafeSocketIOASGI:
    """Wrapper that catches the WebSocket/HTTP response type mismatch.

    python-socketio's Engine.IO ASGI handler sends 'http.response.start'
    on WebSocket scopes when it wants to return a 404. Uvicorn's websockets
    implementation rejects this. We catch it and send a proper
    'websocket.close' instead.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "websocket":
            async def safe_send(message: dict) -> None:
                if message.get("type") == "http.response.start":
                    # Convert to a proper WebSocket close
                    await send({"type": "websocket.close", "code": 1000})
                    return
                if message.get("type") == "http.response.body":
                    # Suppress — the close was already sent above
                    return
                await send(message)

            try:
                await self.app(scope, receive, safe_send)
            except Exception:
                pass
        else:
            await self.app(scope, receive, send)


sio_app = SafeSocketIOASGI(_inner_app)


# ── Connection lifecycle ────────────────────────────────────────

@sio.event
async def connect(sid: str, environ: dict[str, Any], auth: dict[str, Any] | None = None) -> bool:
    """Authenticate the WebSocket connection.

    The frontend sends the session cookie or a token in the `auth` dict.
    For now we accept all connections — auth enforcement will be added
    once the frontend Socket.IO client is wired up.
    """
    print(f"[socket.io] client connected: {sid}")
    return True


@sio.event
async def disconnect(sid: str) -> None:
    print(f"[socket.io] client disconnected: {sid}")


# ── Helper to emit from anywhere ───────────────────────────────

async def emit_to_user(user_id: str, event: str, data: Any) -> None:
    """Send an event to a specific user's room.

    Call `sio.enter_room(sid, user_id)` on connect once auth is enforced.
    """
    await sio.emit(event, data, room=user_id)
