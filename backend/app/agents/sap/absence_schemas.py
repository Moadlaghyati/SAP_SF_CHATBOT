from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class AbsenceIntentResult:
    should_handle: bool
    reason: str
    confidence: float


@dataclass(frozen=True)
class AbsenceRetrievalParams:
    raw_user_question: str
    scope: Literal["employee", "workforce"] = "employee"
    employee_name: str | None = None
    user_id: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    year: int | None = None
    month: int | None = None
    missing_required_fields: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EmployeeAbsence:
    user_id: str
    start_date: str
    end_date: str
    absence_type: str | None = None
    approval_status: str | None = None
    quantity_in_days: float | None = None
    quantity_in_hours: float | None = None
    external_code: str | None = None
    raw: Any = None


@dataclass(frozen=True)
class SapAbsenceSuccessResult:
    handled: Literal[True]
    type: Literal["sap_absences"]
    status: Literal["success"]
    employee: dict[str, str] | None
    date_range: dict[str, str]
    absences: list[EmployeeAbsence]
    summary_text: str


@dataclass(frozen=True)
class SapAbsenceClarificationResult:
    handled: Literal[True]
    type: Literal["sap_absences"]
    status: Literal["needs_clarification"]
    message: str
    missing_fields: list[str]


@dataclass(frozen=True)
class SapAbsenceErrorResult:
    handled: Literal[True]
    type: Literal["sap_absences"]
    status: Literal["error"]
    message: str
    safe_error_code: str | None = None


@dataclass(frozen=True)
class SapAbsenceNotApplicableResult:
    handled: Literal[False]
    type: Literal["sap_absences"]
    status: Literal["not_applicable"]


SapAbsenceResult = (
    SapAbsenceSuccessResult
    | SapAbsenceClarificationResult
    | SapAbsenceErrorResult
    | SapAbsenceNotApplicableResult
)
