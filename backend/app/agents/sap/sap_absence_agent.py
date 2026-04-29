from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from app.agents.sap.absence_extraction import extract_absence_retrieval_params
from app.agents.sap.absence_formatter import format_absence_summary, format_workforce_absence_summary
from app.agents.sap.absence_intent import detect_absence_intent
from app.agents.sap.absence_schemas import (
    SapAbsenceClarificationResult,
    SapAbsenceErrorResult,
    SapAbsenceNotApplicableResult,
    SapAbsenceResult,
    SapAbsenceSuccessResult,
)
from app.services.errors import ConnectorUnavailableError


class SapAbsenceAgent:
    def __init__(self, *, client, current_date_provider):
        self._client = client
        self._current_date_provider = current_date_provider

    async def handle(
        self,
        message: str,
        step_recorder: Callable[[str, str, str, dict[str, Any] | None], None] | None = None,
    ) -> SapAbsenceResult:
        def record(step: str, status: str, detail: str, data: dict[str, Any] | None = None) -> None:
            if step_recorder is not None:
                step_recorder(step, status, detail, data)

        record("sap_absence_intent", "running", "Checking dedicated SAP absence intent.")
        intent = detect_absence_intent(message)
        if not intent.should_handle:
            record(
                "sap_absence_intent",
                "stopped",
                "The dedicated SAP absence agent did not handle this message.",
                {"confidence": intent.confidence, "reason": intent.reason},
            )
            return SapAbsenceNotApplicableResult(
                handled=False,
                type="sap_absences",
                status="not_applicable",
            )
        record(
            "sap_absence_intent",
            "completed",
            "The message is an absence-related SAP request.",
            {"confidence": intent.confidence, "reason": intent.reason},
        )

        current_date = self._current_date_provider()
        if not isinstance(current_date, date):
            current_date = date.today()

        record("sap_parameter_extraction", "running", "Extracting employee identifier and date range from the request.")
        params = extract_absence_retrieval_params(message, current_date=current_date)
        record(
            "sap_parameter_extraction",
            "completed" if not params.missing_required_fields else "needs_clarification",
            "Extracted SAP absence retrieval parameters.",
            {
                "employee_name": params.employee_name,
                "user_id_present": bool(params.user_id),
                "start_date": params.start_date,
                "end_date": params.end_date,
                "scope": params.scope,
                "missing_required_fields": params.missing_required_fields,
            },
        )
        if params.missing_required_fields:
            return SapAbsenceClarificationResult(
                handled=True,
                type="sap_absences",
                status="needs_clarification",
                message=params.clarification_message or "Please provide an employee userId or a full employee name before I query SAP absences.",
                missing_fields=params.missing_required_fields,
            )

        if params.scope == "workforce":
            assert params.start_date is not None
            assert params.end_date is not None
            try:
                record(
                    "sap_absence_query",
                    "running",
                    "Fetching OAuth token if needed, then querying SuccessFactors EmployeeTime for all matching employee records.",
                    {"scope": "workforce", "start_date": params.start_date, "end_date": params.end_date},
                )
                absences = await self._client.get_absences(
                    start_date=params.start_date,
                    end_date=params.end_date,
                )
            except ConnectorUnavailableError as exc:
                record(
                    "sap_absence_query",
                    "error",
                    "SAP workforce absence query failed.",
                    {"safe_error_code": "sap_unavailable"},
                )
                return SapAbsenceErrorResult(
                    handled=True,
                    type="sap_absences",
                    status="error",
                    message=str(exc),
                    safe_error_code="sap_unavailable",
                )

            record(
                "sap_absence_query",
                "completed",
                "SuccessFactors EmployeeTime workforce query completed and results were normalized.",
                {"absence_count": len(absences)},
            )
            record("sap_response_formatting", "completed", "Formatted a safe workforce absence summary.")
            return SapAbsenceSuccessResult(
                handled=True,
                type="sap_absences",
                status="success",
                employee=None,
                date_range={"startDate": params.start_date, "endDate": params.end_date},
                absences=absences,
                summary_text=format_workforce_absence_summary(
                    start_date=params.start_date,
                    end_date=params.end_date,
                    absences=absences,
                ),
            )

        user_id = params.user_id
        if not user_id and params.employee_name:
            try:
                record(
                    "sap_user_resolution",
                    "running",
                    "Resolving employee name to SuccessFactors userId.",
                    {"employee_name": params.employee_name},
                )
                user_id = await self._client.resolve_user_id_by_name(params.employee_name)
            except ConnectorUnavailableError:
                record(
                    "sap_user_resolution",
                    "needs_clarification",
                    "Name lookup is unavailable or not configured.",
                    {"employee_name": params.employee_name},
                )
                return SapAbsenceClarificationResult(
                    handled=True,
                    type="sap_absences",
                    status="needs_clarification",
                    message=(
                        "I found an employee name, but SAP name lookup is not available. "
                        "Please provide the employee userId or configure the SuccessFactors User lookup endpoint."
                    ),
                    missing_fields=["user_id"],
                )
            if not user_id:
                record(
                    "sap_user_resolution",
                    "needs_clarification",
                    "Employee name did not resolve to exactly one SAP userId.",
                    {"employee_name": params.employee_name},
                )
                return SapAbsenceClarificationResult(
                    handled=True,
                    type="sap_absences",
                    status="needs_clarification",
                    message=(
                        "I could not resolve that employee name to exactly one SAP userId. "
                        "Please provide the employee userId."
                    ),
                    missing_fields=["user_id"],
                )

            record(
                "sap_user_resolution",
                "completed",
                "Resolved employee name to a SAP userId.",
                {"employee_name": params.employee_name, "user_id_present": True},
            )

        assert user_id is not None
        assert params.start_date is not None
        assert params.end_date is not None

        try:
            record(
                "sap_absence_query",
                "running",
                "Fetching OAuth token if needed, then querying SuccessFactors EmployeeTime.",
                {"user_id_present": True, "start_date": params.start_date, "end_date": params.end_date},
            )
            absences = await self._client.get_employee_absences(
                user_id=user_id,
                start_date=params.start_date,
                end_date=params.end_date,
            )
        except ConnectorUnavailableError as exc:
            record(
                "sap_absence_query",
                "error",
                "SAP absence query failed.",
                {"safe_error_code": "sap_unavailable"},
            )
            return SapAbsenceErrorResult(
                handled=True,
                type="sap_absences",
                status="error",
                message=str(exc),
                safe_error_code="sap_unavailable",
            )

        record(
            "sap_absence_query",
            "completed",
            "SuccessFactors EmployeeTime query completed and results were normalized.",
            {"absence_count": len(absences)},
        )
        record("sap_response_formatting", "completed", "Formatted a safe absence summary for the assistant response.")
        return SapAbsenceSuccessResult(
            handled=True,
            type="sap_absences",
            status="success",
            employee={"userId": user_id, **({"name": params.employee_name} if params.employee_name else {})},
            date_range={"startDate": params.start_date, "endDate": params.end_date},
            absences=absences,
            summary_text=format_absence_summary(
                user_id=user_id,
                start_date=params.start_date,
                end_date=params.end_date,
                absences=absences,
                employee_name=params.employee_name,
            ),
        )
