"""Socket.IO server.

Mounted as an ASGI sub-app on FastAPI under `/ws`.
Provides best-effort realtime events for sync progress and inbox updates.
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
    """Wrap Socket.IO ASGI app and normalize websocket mismatch edge cases."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "websocket":

            async def safe_send(message: dict) -> None:
                if message.get("type") == "http.response.start":
                    await send({"type": "websocket.close", "code": 1000})
                    return
                if message.get("type") == "http.response.body":
                    return
                await send(message)

            try:
                await self.app(scope, receive, safe_send)
            except Exception:
                # Avoid crashing the whole app on websocket transport edge cases.
                pass
            return

        await self.app(scope, receive, send)


sio_app = SafeSocketIOASGI(_inner_app)


@sio.event
async def connect(sid: str, environ: dict[str, Any], auth: dict[str, Any] | None = None) -> bool:
    """Accept all socket connections.

    Room-level filtering is handled by explicit `join` calls from the frontend.
    """
    return True


@sio.event
async def disconnect(sid: str) -> None:
    return None


@sio.event
async def join(sid: str, data: dict[str, Any] | None = None) -> None:
    """Join a user-scoped room. Best-effort; auth is enforced at API level."""
    if not data:
        return
    user_id = str(data.get("user_id") or "").strip()
    if not user_id:
        return
    await sio.enter_room(sid, user_id)


@sio.event
async def leave(sid: str, data: dict[str, Any] | None = None) -> None:
    if not data:
        return
    user_id = str(data.get("user_id") or "").strip()
    if not user_id:
        return
    await sio.leave_room(sid, user_id)


async def emit_to_user(user_id: str, event: str, data: Any) -> None:
    """Emit an event to one user room."""
    await sio.emit(event, data, room=user_id)


async def emit_global(event: str, data: Any) -> None:
    """Broadcast an event to all connected clients."""
    await sio.emit(event, data)
