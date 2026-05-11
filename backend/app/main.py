from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_audit import router as audit_router
from app.api.routes_chat import router as chat_router
from app.api.routes_demo import router as demo_router
from app.api.routes_health import router as health_router
from app.api.routes_requests import router as requests_router
from app.api.routes_upload import router as upload_router
from app.config.settings import get_settings
from app.services.container import AppContainer


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    container = AppContainer(settings)
    await container.startup()
    app.state.container = container
    try:
        yield
    finally:
        await container.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(chat_router, prefix=settings.api_prefix)
    app.include_router(requests_router, prefix=settings.api_prefix)
    app.include_router(audit_router, prefix=settings.api_prefix)
    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(demo_router, prefix=settings.api_prefix)
    app.include_router(upload_router, prefix=settings.api_prefix)
    return app


app = create_app()
