from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_container
from app.schemas.api import HealthResponse
from app.services.container import AppContainer

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(container: AppContainer = Depends(get_container)) -> HealthResponse:
    return await container.health_check()
