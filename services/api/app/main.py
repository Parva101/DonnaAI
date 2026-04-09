from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import TraceIdMiddleware

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title=settings.app_name, version="phase0")
app.add_middleware(TraceIdMiddleware)
app.include_router(router)

