from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_container
from app.schemas.api import (
    DemoUsersResponse,
    LocalModelsResponse,
    SapLoginRequest,
    SwitchLocalModelRequest,
    SwitchLocalModelResponse,
    SwitchUserRequest,
    SwitchUserResponse,
)
from app.services.errors import LocalLLMUnavailableError
from app.services.container import AppContainer

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/users", response_model=DemoUsersResponse)
def list_demo_users(container: AppContainer = Depends(get_container)) -> DemoUsersResponse:
    if container.settings.connector_backend == "successfactors" and container.settings.sap_acting_user_id:
        active_id = container.settings.sap_acting_user_id
    else:
        active_id = container.settings.default_demo_user_id
    return DemoUsersResponse(
        items=container.authorization_service.list_demo_users(),
        active_user_id=active_id,
    )


@router.post("/switch-user", response_model=SwitchUserResponse)
def switch_demo_user(
    payload: SwitchUserRequest,
    container: AppContainer = Depends(get_container),
) -> SwitchUserResponse:
    user = container.demo_user_repository.get_user(payload.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo user not found.")
    return SwitchUserResponse(active_user=user)


@router.post("/sap-login", response_model=SwitchUserResponse)
async def sap_login(
    payload: SapLoginRequest,
    container: AppContainer = Depends(get_container),
) -> SwitchUserResponse:
    try:
        user = await container.sap_login_user(payload.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"SAP lookup failed: {exc}") from exc
    return SwitchUserResponse(active_user=user)


@router.get("/local-models", response_model=LocalModelsResponse)
async def list_local_models(container: AppContainer = Depends(get_container)) -> LocalModelsResponse:
    try:
        items = await container.list_local_models()
    except LocalLLMUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return LocalModelsResponse(
        backend=container.settings.llm_backend,
        active_model=container.active_llm_model(),
        items=items,
    )


@router.post("/switch-model", response_model=SwitchLocalModelResponse)
async def switch_local_model(
    payload: SwitchLocalModelRequest,
    container: AppContainer = Depends(get_container),
) -> SwitchLocalModelResponse:
    try:
        active_model = await container.switch_local_model(payload.model)
    except LocalLLMUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SwitchLocalModelResponse(backend=container.settings.llm_backend, active_model=active_model)
