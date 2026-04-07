from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio

from app.api.router import api_router
from app.core.config import settings
from app.core.db import init_db
from app.core.socketio_server import sio


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.environment != "testing":
        init_db()

        # Start Redis pool (non-blocking — skip if Redis is unreachable)
        try:
            from app.core.redis import init_redis

            await init_redis()
        except Exception:
            import warnings

            warnings.warn("Redis not available — running without cache/pubsub")

    yield

    # Shutdown: close Redis pool
    if settings.environment != "testing":
        try:
            from app.core.redis import close_redis

            await close_redis()
        except Exception:
            pass


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", tags=["meta"])
    def root() -> dict[str, str]:
        return {"message": "DonnaAI backend is running."}

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


fastapi_app = create_app()
app = socketio.ASGIApp(
    sio,
    other_asgi_app=fastapi_app,
    socketio_path="ws/socket.io",
)
