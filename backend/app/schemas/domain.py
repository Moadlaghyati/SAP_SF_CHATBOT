from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RoleType = Literal["employee", "manager", "hr_admin"]
IntentType = Literal["absence_count", "absence_list", "absence_breakdown", "general_chat", "unsupported"]
RequestStatus = Literal[
    "success",
    "clarification_required",
    "forbidden",
    "not_found",
    "unsupported",
    "invalid_input",
    "unavailable",
    "error",
]


class Period(BaseModel):
    start: date
    end: date


class Employee(BaseModel):
    employee_id: str
    display_name: str
    first_name: str
    last_name: str
    email: str
    manager_employee_id: str | None = None
    aliases: list[str] = Field(default_factory=list)
    sap_user_id: str | None = None


class RequestContext(BaseModel):
    request_id: str
    user_id: str
    user_display_name: str
    user_role: RoleType
    employee_id: str | None = None
    allowed_employee_ids: list[str] = Field(default_factory=list)
    timestamp: datetime
    source: str = "demo_ui"


class AbsenceRecord(BaseModel):
    absence_id: str
    employee_id: str
    employee_display_name: str
    absence_type: str
    start_date: date
    end_date: date
    days: float
    status: str = "approved"


class AbsenceTypeBreakdown(BaseModel):
    type: str
    count: int
    days: float


class AbsenceSummary(BaseModel):
    employee_id: str
    employee_display_name: str
    period: Period
    absence_count: int
    absence_days: float
    by_type: list[AbsenceTypeBreakdown] = Field(default_factory=list)


class EmployeeMatch(BaseModel):
    employee_id: str
    display_name: str


class ToolTrace(BaseModel):
    request_id: str
    request_message: str
    process_steps: list[dict[str, Any]] = Field(default_factory=list)
    detected_intent: str | None = None
    parsed_request: dict[str, Any] = Field(default_factory=dict)
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    data_source: str | None = None
    authorization_outcome: str = "pending"
    authorization_reason: str | None = None
    target_employee_id: str | None = None
    target_employee_display_name: str | None = None
    model_inference: str = "local"
    llm_backend: str | None = None
    llm_model: str | None = None
    external_ai_calls: str = "none"
    status: str = "processing"
    errors: list[str] = Field(default_factory=list)
    minimized_result: dict[str, Any] | None = None
    answer_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None


class AuditRecord(BaseModel):
    request_id: str
    timestamp: datetime
    acting_user: str
    user_role: RoleType
    original_question: str
    parsed_intent: str | None = None
    tool_called: str | None = None
    target_employee: str | None = None
    authorization_outcome: str
    final_status: RequestStatus
    duration_ms: int
    data_source: str | None = None


class Holiday(BaseModel):
    date: str
    name: str
    name_fr: str = ""
    type: str = "public"
    country: str = "MA"


class WorkDay(BaseModel):
    day_of_week: str
    start_time: str
    end_time: str
    hours: float


class WorkSchedule(BaseModel):
    employee_id: str
    employee_display_name: str
    schedule_name: str
    work_days: list[WorkDay]
    hours_per_week: float
    days_per_week: int


class ConnectorHealth(BaseModel):
    backend: str
    available: bool
    details: str


class LocalModelSummary(BaseModel):
    name: str
    modified_at: datetime | None = None
    size: int | None = None
    family: str | None = None
    parameter_size: str | None = None
    quantization_level: str | None = None
