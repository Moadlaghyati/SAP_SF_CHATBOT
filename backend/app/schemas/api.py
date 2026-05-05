from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.domain import AuditRecord, LocalModelSummary, RequestStatus, RoleType, ToolTrace


class ChatRequest(BaseModel):
    message: str = Field(min_length=3, max_length=1000)


class ChatResponse(BaseModel):
    request_id: str
    status: RequestStatus
    answer: str
    trace: ToolTrace


class ErrorResponse(BaseModel):
    request_id: str | None = None
    status: RequestStatus
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class RequestListItem(BaseModel):
    request_id: str
    created_at: datetime
    acting_user: str
    user_role: RoleType
    question: str
    parsed_intent: str | None = None
    tool_name: str | None = None
    target_employee_id: str | None = None
    authorization_outcome: str
    status: RequestStatus
    duration_ms: int | None = None


class RequestDetail(BaseModel):
    request_id: str
    created_at: datetime
    acting_user: str
    user_role: RoleType
    question: str
    parsed_intent: str | None = None
    tool_name: str | None = None
    target_employee_id: str | None = None
    authorization_outcome: str
    status: RequestStatus
    duration_ms: int | None = None
    answer: str | None = None
    trace: ToolTrace | None = None


class RequestListResponse(BaseModel):
    items: list[RequestListItem]


class AuditListResponse(BaseModel):
    items: list[AuditRecord]


class DemoUserSummary(BaseModel):
    user_id: str
    display_name: str
    role: RoleType
    job_title: str = ""
    employee_id: str | None = None
    description: str


class DemoUsersResponse(BaseModel):
    items: list[DemoUserSummary]
    active_user_id: str | None = None


class SwitchUserRequest(BaseModel):
    user_id: str


class SwitchUserResponse(BaseModel):
    active_user: DemoUserSummary


class LocalModelsResponse(BaseModel):
    backend: str
    active_model: str | None = None
    items: list[LocalModelSummary]


class SwitchLocalModelRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)


class SwitchLocalModelResponse(BaseModel):
    backend: str
    active_model: str


class HealthComponent(BaseModel):
    name: str
    ok: bool
    details: str


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    connector_backend: str
    llm_backend: str
    llm_model: str | None = None
    model_inference: str = "local"
    external_ai_calls: str = "none"
    components: list[HealthComponent]
