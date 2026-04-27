from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_container, get_demo_user_id
from app.schemas.api import ChatRequest, ChatResponse
from app.services.container import AppContainer

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    container: AppContainer = Depends(get_container),
    demo_user_id: str = Depends(get_demo_user_id),
) -> ChatResponse:
    return await container.orchestrator.handle_message(payload.message, demo_user_id)
