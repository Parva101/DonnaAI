"""Socket.IO server.

Exposed by wrapping FastAPI app with `socketio.ASGIApp` in `app.main`.
Provides best-effort realtime events for sync progress and inbox updates.
"""

from __future__ import annotations

import socketio

from app.core.config import settings


sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.cors_origins,
    logger=False,
    engineio_logger=False,
)


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
