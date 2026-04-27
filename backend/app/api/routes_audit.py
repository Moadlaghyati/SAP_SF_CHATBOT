from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_container
from app.schemas.api import AuditListResponse
from app.services.container import AppContainer

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=AuditListResponse)
def list_audit_records(container: AppContainer = Depends(get_container)) -> AuditListResponse:
    return AuditListResponse(items=container.audit_repository.list_records())
