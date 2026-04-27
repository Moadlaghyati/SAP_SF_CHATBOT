from __future__ import annotations

import asyncio
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.api.routes_audit import router as audit_router
from app.api.routes_chat import router as chat_router
from app.api.routes_demo import router as demo_router
from app.api.routes_health import router as health_router
from app.api.routes_requests import router as requests_router
from app.config.settings import Settings
from app.services.container import AppContainer


@pytest.fixture
def test_settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        llm_backend="mock",
        connector_backend="mock",
        connector_mock_latency_ms=0,
        default_demo_user_id="demo_manager_meryem",
    )


@pytest.fixture
def container(test_settings: Settings):
    app_container = AppContainer(test_settings)
    asyncio.run(app_container.startup())
    try:
        yield app_container
    finally:
        asyncio.run(app_container.shutdown())


@pytest.fixture
def test_app(container: AppContainer, test_settings: Settings) -> FastAPI:
    app = FastAPI(title="Test HR AI Assistant")
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=test_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(chat_router, prefix=test_settings.api_prefix)
    app.include_router(requests_router, prefix=test_settings.api_prefix)
    app.include_router(audit_router, prefix=test_settings.api_prefix)
    app.include_router(health_router, prefix=test_settings.api_prefix)
    app.include_router(demo_router, prefix=test_settings.api_prefix)
    return app


@pytest.fixture
def client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(test_app) as test_client:
        yield test_client
