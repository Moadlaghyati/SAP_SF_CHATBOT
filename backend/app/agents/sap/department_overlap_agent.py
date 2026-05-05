from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from typing import Any

from app.agents.sap.absence_extraction import extract_absence_retrieval_params
from app.agents.sap.absence_schemas import (
    EmployeeAbsence,
    SapDepartmentOverlapClarificationResult,
    SapDepartmentOverlapErrorResult,
    SapDepartmentOverlapNotApplicableResult,
    SapDepartmentOverlapResult,
    SapDepartmentOverlapSuccessResult,
)
from app.services.errors import ConnectorUnavailableError


_OVERLAP_PATTERNS = [
    r"\bsame\s+department\b",
    r"\bsame\s+team\b",
    r"\bcolleagues?\b.*\b(?:absent|on\s+leave|off)\b",
    r"\b(?:absent|on\s+leave|off)\b.*\bcolleagues?\b",
    r"\bwho\s+else\b.*\b(?:absent|on\s+leave|on\s+vacation|off)\b",
    r"\bother\s+employees?\b.*\b(?:same\s+)?(?:department|team)\b",
    r"\b(?:department|team)\b.*\babsence\b.*\boverlap\b",
    r"\bdepartment\s+overlap\b",
    r"\bteam\s+overlap\b",
    r"\b(?:anyone|any\s+one|anybody)\b.*\bsame\s+(?:department|team)\b",
    r"\bsame\s+(?:department|team)\b.*\b(?:anyone|any\s+one|anybody|absent|on\s+leave)\b",
    r"\bin\s+(?:the\s+)?(?:same\s+)?(?:department|team)\b.*\babsent\b",
    r"\babsent\b.*\bin\s+(?:the\s+)?(?:same\s+)?(?:department|team)\b",
    r"\b(?:department|team)\b.*\b(?:members?|colleagues?|employees?)\b.*\babsent\b",
    # "in Walid's department", "in John Smith's team", "in the HR department"
    r"\bin\s+(?:the\s+)?[\w][\w' -]*?(?:'s)?\s+(?:department|team|group)\b",
    # "anyone in Walid's department absent"
    r"\b(?:anyone|any\s+one|anybody|someone|somebody)\b.*\b(?:department|team)\b.*\b(?:absent|on\s+leave|off)\b",
    # "absent in [name]'s department"
    r"\b(?:absent|on\s+leave|off)\b.*\bin\s+[\w][\w' -]*?(?:'s)?\s+(?:department|team)\b",
]


def detect_department_overlap_intent(message: str) -> bool:
    lowered = message.lower()
    return any(re.search(pattern, lowered, re.IGNORECASE) for pattern in _OVERLAP_PATTERNS)


_DEPT_NAME_PATTERNS = [
    r"\bin\s+(?:the\s+)?([A-Za-z][A-Za-z' -]+?)(?:'s)?\s+(?:department|team|group)\b",
    r"\b(?:department|team)\s+of\s+([A-Za-z][A-Za-z' -]+?)\s*(?:\?|$|\b(?:absent|on\s+leave))",
]


def _extract_employee_name_from_department_phrase(text: str) -> str | None:
    for pattern in _DEPT_NAME_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip().title()
            if len(candidate) >= 2 and not re.search(r"\d", candidate):
                return candidate
    return None


class DepartmentOverlapAgent:
    def __init__(self, *, client, current_date_provider):
        self._client = client
        self._current_date_provider = current_date_provider

    async def handle(
        self,
        message: str,
        step_recorder: Callable[[str, str, str, dict[str, Any] | None], None] | None = None,
    ) -> SapDepartmentOverlapResult:
        def record(step: str, status: str, detail: str, data: dict[str, Any] | None = None) -> None:
            if step_recorder is not None:
                step_recorder(step, status, detail, data)

        record("dept_overlap_intent", "running", "Checking for department overlap intent.")
        if not detect_department_overlap_intent(message):
            record("dept_overlap_intent", "stopped", "Not a department overlap request.")
            return SapDepartmentOverlapNotApplicableResult(
                handled=False,
                type="department_overlap",
                status="not_applicable",
            )
        record("dept_overlap_intent", "completed", "Detected department overlap intent.")

        current_date = self._current_date_provider()
        if not isinstance(current_date, date):
            current_date = date.today()

        record("dept_overlap_param_extraction", "running", "Extracting employee and date range from request.")
        params = extract_absence_retrieval_params(message, current_date=current_date)
        record(
            "dept_overlap_param_extraction",
            "completed",
            "Extracted parameters for department overlap query.",
            {
                "employee_name": params.employee_name,
                "user_id_present": bool(params.user_id),
                "start_date": params.start_date,
                "end_date": params.end_date,
            },
        )

        user_id = params.user_id
        employee_name = params.employee_name or _extract_employee_name_from_department_phrase(message)

        if not user_id and not employee_name:
            return SapDepartmentOverlapClarificationResult(
                handled=True,
                type="department_overlap",
                status="needs_clarification",
                message=(
                    "Please specify the employee (by name or userId) whose department "
                    "you want to check for absence overlaps."
                ),
                missing_fields=["employee_identifier"],
            )

        if not user_id and employee_name:
            if len(employee_name.strip().split()) < 2:
                return SapDepartmentOverlapClarificationResult(
                    handled=True,
                    type="department_overlap",
                    status="needs_clarification",
                    message=(
                        f"I found the name '{employee_name}' but need the full name "
                        f"(first and last name) or the employee's userId to look them up. "
                        f"For example: \"Is there anyone in Walid Regragi's department absent in March 2026?\""
                    ),
                    missing_fields=["employee_full_name"],
                )
            try:
                record(
                    "dept_overlap_user_resolution",
                    "running",
                    "Resolving employee name to userId.",
                    {"employee_name": employee_name},
                )
                user_id = await self._client.resolve_user_id_by_name(employee_name)
            except ConnectorUnavailableError:
                return SapDepartmentOverlapClarificationResult(
                    handled=True,
                    type="department_overlap",
                    status="needs_clarification",
                    message=(
                        "Name lookup is unavailable. "
                        "Please provide the employee's userId instead."
                    ),
                    missing_fields=["user_id"],
                )
            if not user_id:
                return SapDepartmentOverlapClarificationResult(
                    handled=True,
                    type="department_overlap",
                    status="needs_clarification",
                    message=(
                        f"Could not resolve '{employee_name}' to a unique SAP user. "
                        "Please provide the employee's userId."
                    ),
                    missing_fields=["user_id"],
                )
            record(
                "dept_overlap_user_resolution",
                "completed",
                "Resolved name to userId.",
                {"user_id_present": True},
            )

        assert user_id is not None

        start_date = params.start_date
        end_date = params.end_date
        if not start_date or not end_date:
            return SapDepartmentOverlapClarificationResult(
                handled=True,
                type="department_overlap",
                status="needs_clarification",
                message=(
                    "Please specify the date or date range to check for department absence overlaps."
                ),
                missing_fields=["date_range"],
            )

        try:
            record(
                "dept_overlap_dept_lookup",
                "running",
                "Looking up employee department.",
                {"user_id": user_id},
            )
            department = await self._client.get_employee_department(user_id=user_id)
        except ConnectorUnavailableError as exc:
            return SapDepartmentOverlapErrorResult(
                handled=True,
                type="department_overlap",
                status="error",
                message=str(exc),
                safe_error_code="sap_unavailable",
            )

        if not department:
            record("dept_overlap_dept_lookup", "stopped", "No department found for employee.")
            return SapDepartmentOverlapClarificationResult(
                handled=True,
                type="department_overlap",
                status="needs_clarification",
                message=(
                    f"Could not determine the department for '{employee_name or user_id}'. "
                    "The employee may not have an active job record in SuccessFactors."
                ),
                missing_fields=["department"],
            )
        record(
            "dept_overlap_dept_lookup",
            "completed",
            "Found employee department.",
            {"department": department},
        )

        try:
            record(
                "dept_overlap_members_lookup",
                "running",
                "Fetching department members.",
                {"department": department},
            )
            dept_user_ids = await self._client.get_department_employees(department=department)
        except ConnectorUnavailableError as exc:
            return SapDepartmentOverlapErrorResult(
                handled=True,
                type="department_overlap",
                status="error",
                message=str(exc),
                safe_error_code="sap_unavailable",
            )

        other_user_ids = [uid for uid in dept_user_ids if uid != user_id]
        record(
            "dept_overlap_members_lookup",
            "completed",
            "Fetched department members.",
            {"total_in_dept": len(dept_user_ids), "others": len(other_user_ids)},
        )

        all_absences: list[EmployeeAbsence] = []
        record(
            "dept_overlap_absence_query",
            "running",
            "Fetching absences for department members.",
            {"start_date": start_date, "end_date": end_date, "member_count": len(other_user_ids)},
        )
        for uid in other_user_ids:
            try:
                member_absences = await self._client.get_employee_absences(
                    user_id=uid,
                    start_date=start_date,
                    end_date=end_date,
                )
                all_absences.extend(member_absences)
            except ConnectorUnavailableError:
                pass

        record(
            "dept_overlap_absence_query",
            "completed",
            "Fetched department absence records.",
            {"absence_count": len(all_absences)},
        )

        # Resolve display names for all employees who appear in the absences
        absent_user_ids = list({a.user_id for a in all_absences if a.user_id})
        record(
            "dept_overlap_name_resolution",
            "running",
            "Resolving display names for absent department members.",
            {"count": len(absent_user_ids)},
        )
        try:
            member_names = await self._client.get_display_names_for_user_ids(absent_user_ids)
        except Exception:
            member_names = {}
        record(
            "dept_overlap_name_resolution",
            "completed",
            "Resolved display names.",
            {"resolved": len(member_names)},
        )

        target_employee_dict: dict[str, str] = {"userId": user_id}
        if employee_name:
            target_employee_dict["name"] = employee_name

        summary = _format_summary(
            target_employee=target_employee_dict,
            department=department,
            start_date=start_date,
            end_date=end_date,
            absences=all_absences,
            member_names=member_names,
        )

        return SapDepartmentOverlapSuccessResult(
            handled=True,
            type="department_overlap",
            status="success",
            target_employee=target_employee_dict,
            department=department,
            date_range={"startDate": start_date, "endDate": end_date},
            absences=all_absences,
            member_names=member_names,
            summary_text=summary,
        )


def _format_summary(
    *,
    target_employee: dict[str, str],
    department: str,
    start_date: str,
    end_date: str,
    absences: list[EmployeeAbsence],
    member_names: dict[str, str] | None = None,
) -> str:
    names = member_names or {}
    emp_label = target_employee.get("name") or target_employee.get("userId") or "the employee"
    period = start_date if start_date == end_date else f"{start_date} to {end_date}"
    if not absences:
        return (
            f"No other employees in the '{department}' department are absent during {period} "
            f"(the same period as {emp_label})."
        )
    lines = [
        f"Found {len(absences)} absence record{'s' if len(absences) != 1 else ''} "
        f"for other employees in the '{department}' department during {period}:"
    ]
    for i, absence in enumerate(absences, start=1):
        display = names.get(absence.user_id) or f"User {absence.user_id}"
        absence_type = absence.absence_type or "Absence"
        status = absence.approval_status or "Status unavailable"
        lines.append(
            f"{i}. {display} — {absence_type} "
            f"— {absence.start_date} to {absence.end_date} — {status}"
        )
    return "\n".join(lines)
