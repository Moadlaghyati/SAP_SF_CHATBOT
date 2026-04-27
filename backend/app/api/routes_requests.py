from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_container
from app.schemas.api import RequestDetail, RequestListResponse
from app.services.container import AppContainer

router = APIRouter(tags=["requests"])


@router.get("/requests", response_model=RequestListResponse)
def list_requests(container: AppContainer = Depends(get_container)) -> RequestListResponse:
    return RequestListResponse(items=container.request_repository.list_requests(container.settings.request_history_limit))


@router.get("/requests/{request_id}", response_model=RequestDetail)
def get_request(request_id: str, container: AppContainer = Depends(get_container)) -> RequestDetail:
    item = container.request_repository.get_request(request_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")
    return item
