from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, is_dataclass
from datetime import date
from uuid import uuid4

LOGGER = logging.getLogger(__name__)

from app.agents.sap.absence_schemas import SapAbsenceResult, SapDepartmentOverlapResult
from app.agents.sap.schedule_agent import ScheduleAgent
from app.connectors.mock_data import MOCK_EMPLOYEES
from pydantic import ValidationError

from app.audit.service import AuditService
from app.auth.service import AuthorizationService
from app.config.settings import Settings
from app.llm.base import LocalLLMClient
from app.repositories.request_repository import RequestRepository
from app.schemas.api import ChatResponse
from app.schemas.domain import Employee, RequestStatus, ToolTrace
from app.schemas.llm import AnswerGenerationPayload, ParsedQuestion
from app.services.errors import ConnectorUnavailableError, DemoUserNotFoundError, LocalLLMUnavailableError, StructuredOutputError
from app.services.time import utc_now
from app.tools.service import ToolService


_TIME_TYPE_MAP: dict[str, tuple[str, str]] = {
    # Morocco-specific codes (primary for this SAP instance)
    "annual leave": ("MAR_VACATION", "Vacation"),
    "annual": ("MAR_VACATION", "Vacation"),
    "vacation": ("MAR_VACATION", "Vacation"),
    "congé annuel": ("MAR_VACATION", "Vacation"),
    "conge annuel": ("MAR_VACATION", "Vacation"),
    "paid leave": ("MA_P.LEAVE", "Paid leave"),
    "congé payé": ("MA_P.LEAVE", "Paid leave"),
    "sick leave": ("MAR_Sick_Leave", "Sick Leave"),
    "sick": ("MAR_Sick_Leave", "Sick Leave"),
    "sickness": ("MAR_Sick_Leave", "Sick Leave"),
    "illness": ("MA_SICK", "Sick leave"),
    "arrêt maladie": ("MAR_Sick_Leave", "Sick Leave"),
    "maladie": ("MAR_Sick_Leave", "Sick Leave"),
    "unpaid leave": ("MA_UNPAIDLEAVE", "Unpaid Leave"),
    "unpaid": ("MA_UNPAIDLEAVE", "Unpaid Leave"),
    "sans solde": ("MA_UNPAIDLEAVE", "Unpaid Leave"),
    "maternity leave": ("MAR_MATLEAV", "Maternity leave"),
    "maternity": ("MAR_MATLEAV", "Maternity leave"),
    "maternité": ("MAR_MATLEAV", "Maternity leave"),
    "paternity leave": ("MAR_PATLEAV", "Paternity leave"),
    "paternity": ("MAR_PATLEAV", "Paternity leave"),
    "paternité": ("MAR_PATLEAV", "Paternity leave"),
    "family reasons": ("MA_FAMREAS", "Family reasons"),
    "family": ("MA_FAMREAS", "Family reasons"),
    "famille": ("MA_FAMREAS", "Family reasons"),
    "marriage leave": ("MAR_MARLEAV", "Marriage Leave"),
    "marriage": ("MAR_MARLEAV", "Marriage Leave"),
    "mariage": ("MAR_MARLEAV", "Marriage Leave"),
    "time off in lieu": ("MAR_DAYOFF", "Day/time off in lieu"),
    "toil": ("MAR_DAYOFF", "Day/time off in lieu"),
    "doctor": ("MAR_DOCVT", "Doctor's visit / Medical test"),
    "doctor appointment": ("MAR_DOCVT", "Doctor's visit / Medical test"),
    "medical": ("MAR_DOCVT", "Doctor's visit / Medical test"),
    "remote work": ("MA_REMOTE_WORK", "Remote Work"),
    "telework": ("MA_REMOTE_WORK", "Remote Work"),
    "télétravail": ("MA_REMOTE_WORK", "Remote Work"),
    "justified absence": ("MAR_JUSTABS", "Justified absence"),
    "force majeure": ("MAR_FORCEMAJEURE", "Force majeure"),
}


def _resolve_time_type(absence_type: str | None) -> tuple[str | None, str]:
    if not absence_type:
        return None, ""
    key = absence_type.lower().strip()
    match = _TIME_TYPE_MAP.get(key)
    if match:
        return match
    for k, v in _TIME_TYPE_MAP.items():
        if k in key or key in k:
            return v
    return None, ""


class ChatOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        authorization_service: AuthorizationService,
        tool_service: ToolService,
        request_repository: RequestRepository,
        audit_service: AuditService,
        llm_client: LocalLLMClient,
        sap_absence_agent=None,
        dept_overlap_agent=None,
        sap_employee_id_map: dict[str, str] | None = None,
        sap_all_user_ids: list[str] | None = None,
        sap_client=None,
    ):
        self._settings = settings
        self._authorization_service = authorization_service
        self._tool_service = tool_service
        self._request_repository = request_repository
        self._audit_service = audit_service
        self._llm_client = llm_client
        self._sap_absence_agent = sap_absence_agent
        self._dept_overlap_agent = dept_overlap_agent
        self._sap_client = sap_client
        self._schedule_agent: ScheduleAgent | None = (
            ScheduleAgent(client=sap_client) if sap_client else None
        )
        # Shared reference to the container's map — populated at startup
        self._sap_employee_id_map: dict[str, str] = sap_employee_id_map if sap_employee_id_map is not None else {}
        # All SAP user IDs fetched at startup — used for workforce queries
        self._sap_all_user_ids: list[str] = sap_all_user_ids if sap_all_user_ids is not None else []

    async def handle_message(
        self,
        message: str,
        user_id: str,
        sap_record_key: str | None = None,
        pending_attachments: dict | None = None,
    ) -> ChatResponse:
        request_id = f"req_{uuid4().hex[:12]}"
        context = None
        trace = ToolTrace(
            request_id=request_id,
            request_message=message,
            llm_backend=self._llm_client.backend_name,
            llm_model=self._settings.ollama_model if self._llm_client.backend_name == "ollama" else "mock",
            data_source=self._tool_service.connector_backend,
            created_at=utc_now(),
        )
        self._record_step(trace, "received", "completed", "User message received by backend.")
        started = time.perf_counter()
        parsed_question: ParsedQuestion | None = None
        target_employee: Employee | None = None
        tool_name: str | None = None
        authorization_outcome = "pending"
        status: RequestStatus = "error"
        answer = "The request could not be completed."

        try:
            context = self._authorization_service.build_request_context(request_id, user_id)
            self._record_step(trace, "request_context", "completed", "Demo request context and acting user loaded.")
            self._request_repository.create_request(
                request_id=request_id,
                acting_user_id=context.user_id,
                acting_user_name=context.user_display_name,
                acting_user_role=context.user_role,
                question=message,
            )

            if self._dept_overlap_agent is not None:
                self._record_step(trace, "dept_overlap_agent", "running", "Checking for department overlap intent.")
                dept_result = await self._dept_overlap_agent.handle(
                    message,
                    step_recorder=lambda name, step_status, detail, data=None: self._record_step(
                        trace, name, step_status, detail, data
                    ),
                )
                if dept_result.handled:
                    self._record_step(
                        trace,
                        "dept_overlap_agent",
                        "completed" if dept_result.status == "success" else dept_result.status,
                        "Department Overlap Agent returned a structured result.",
                        {"result_status": dept_result.status},
                    )
                    parsed_question = self._dept_overlap_result_to_parsed_question(dept_result)
                    trace.detected_intent = "department_overlap"
                    trace.parsed_request = {"agent_result_status": dept_result.status}
                    trace.tool_name = "dept_overlap_agent"
                    trace.authorization_outcome = "not_applicable"
                    trace.status = self._dept_overlap_result_to_request_status(dept_result)
                    trace.minimized_result = self._minimize_dept_overlap_result(dept_result)
                    status = trace.status  # type: ignore[assignment]
                    authorization_outcome = trace.authorization_outcome
                    if dept_result.status == "success":
                        answer = await self._generate_answer(
                            parsed_question=parsed_question,
                            status=status,
                            employee=None,
                            result=self._minimize_dept_overlap_result(dept_result),
                            error_message=None,
                            clarification_options=[],
                            user_message=message,
                        )
                    else:
                        answer = self._dept_overlap_result_to_answer(dept_result)
                    return await self._finalize(
                        trace=trace,
                        request_id=request_id,
                        answer=answer,
                        parsed_question=parsed_question,
                        tool_name=trace.tool_name,
                        target_employee=None,
                        authorization_outcome=authorization_outcome,
                        status=status,
                        started=started,
                        message=message,
                        context_user=context,
                    )

            # ── Step 1: LLM Intent Analysis ──────────────────────────────────────────────
            acting_sap_id = self._resolve_sap_id(context.employee_id) or self._settings.sap_acting_user_id
            self._record_step(trace, "intent_analysis", "running", "Analyzing intent with LLM (step 1 of 2).")
            structured_intent = await self._llm_client.analyze_intent(
                message,
                current_date=date.today(),
                acting_user_display_name=context.user_display_name,
            )
            LOGGER.info(
                "[Intent] intent=%s employee_ref=%s required_api=%s clarification=%s",
                structured_intent.intent, structured_intent.employee_reference,
                structured_intent.required_api, structured_intent.clarification_needed,
            )
            self._record_step(
                trace, "intent_analysis", "completed",
                f"Detected intent: {structured_intent.intent}",
                {
                    "intent": structured_intent.intent,
                    "employee_reference": structured_intent.employee_reference,
                    "required_api": structured_intent.required_api,
                    "clarification_needed": structured_intent.clarification_needed,
                },
            )
            trace.detected_intent = structured_intent.intent
            trace.parsed_request = structured_intent.model_dump()

            # ── Clarification ─────────────────────────────────────────────────────────────
            if structured_intent.clarification_needed:
                answer = structured_intent.clarification_question or "Could you please provide more details about your request?"
                status = "clarification_required"
                authorization_outcome = "needs_clarification"
                trace.authorization_outcome = authorization_outcome
                trace.status = status
                return await self._finalize(
                    trace=trace, request_id=request_id, answer=answer,
                    parsed_question=ParsedQuestion(intent="general_chat", needs_clarification=True,
                                                    clarification_reason=answer),
                    tool_name=None, target_employee=None,
                    authorization_outcome=authorization_outcome, status=status,
                    started=started, message=message, context_user=context,
                )

            # ── Step 2: Route to SAP API ──────────────────────────────────────────────────
            self._record_step(trace, "sap_api_routing", "running",
                              f"Routing to SAP API for intent: {structured_intent.intent}",
                              {"intent": structured_intent.intent, "api": structured_intent.required_api})

            if structured_intent.intent == "leave_balance":
                answer, status, sap_result = await self._handle_leave_balance(
                    structured_intent, acting_sap_id, context, message, trace)

            elif structured_intent.intent == "approval_status":
                answer, status, sap_result = await self._handle_approval_status(
                    structured_intent, acting_sap_id, context, message, trace)

            elif structured_intent.intent in {"upcoming_absences", "absence_history", "team_absences"}:
                answer, status, sap_result = await self._handle_absence_query(
                    structured_intent, acting_sap_id, context, message, trace)

            elif structured_intent.intent == "create_absence_request":
                answer, status, sap_result = await self._handle_create_absence_request(
                    structured_intent, acting_sap_id, context, message, trace,
                    sap_record_key=sap_record_key,
                    pending_attachments=pending_attachments,
                )

            elif structured_intent.intent == "cancel_absence_request":
                # TODO: implement cancel via SAP EmployeeTime DELETE/PATCH
                answer = "Cancelling absence requests via chat is not yet available. Please use the SAP SuccessFactors portal."
                status = "unsupported"
                sap_result = {}

            elif structured_intent.intent in {"holiday_query", "work_schedule_query"}:
                answer, status, sap_result = await self._handle_schedule_query(
                    structured_intent, acting_sap_id, context, message, trace)

            else:  # unknown → general chat
                answer, status, sap_result = await self._handle_general_chat_intent(message, context, trace)

            authorization_outcome = "not_applicable"
            trace.authorization_outcome = authorization_outcome
            trace.status = status
            trace.minimized_result = sap_result

            parsed_question = ParsedQuestion(
                intent="general_chat",
                needs_clarification=False,
            )

            return await self._finalize(
                trace=trace, request_id=request_id, answer=answer,
                parsed_question=parsed_question, tool_name=structured_intent.required_api,
                target_employee=None, authorization_outcome=authorization_outcome,
                status=status, started=started, message=message, context_user=context,
            )

        except DemoUserNotFoundError as exc:
            status = "invalid_input"
            authorization_outcome = "invalid_user"
            trace.errors.append(str(exc))
            answer = str(exc)
        except (ValidationError, StructuredOutputError) as exc:
            status = "invalid_input"
            authorization_outcome = "validation_failed"
            trace.errors.append(str(exc))
            answer = "I could not safely interpret that request. Please include an employee and a clear date range."
        except (LocalLLMUnavailableError, ConnectorUnavailableError) as exc:
            status = "unavailable"
            authorization_outcome = "unavailable"
            trace.errors.append(str(exc))
            answer = str(exc)
        except Exception as exc:  # pragma: no cover - defensive fallback
            status = "error"
            authorization_outcome = "error"
            trace.errors.append(str(exc))
            answer = "An unexpected error occurred while handling the request."

        trace.authorization_outcome = authorization_outcome
        trace.status = status
        if status in {"error", "invalid_input", "unavailable"}:
            self._record_step(trace, "finalize", status, "Request ended before successful completion.")
        return await self._finalize(
            trace=trace,
            request_id=request_id,
            answer=answer,
            parsed_question=parsed_question,
            tool_name=tool_name,
            target_employee=target_employee,
            authorization_outcome=authorization_outcome,
            status=status,
            started=started,
            message=message,
            context_user=context,
        )

    async def _run_tool(
        self, parsed_question: ParsedQuestion, target_employee: Employee
    ) -> tuple[str, dict]:
        assert parsed_question.start_date is not None
        assert parsed_question.end_date is not None

        if parsed_question.intent in {"absence_count", "absence_breakdown"}:
            summary = await self._tool_service.count_absences(
                employee_id=target_employee.employee_id,
                start_date=parsed_question.start_date,
                end_date=parsed_question.end_date,
                absence_type=parsed_question.absence_type,
            )
            minimized = summary.model_dump(mode="json")
            minimized["absence_type"] = parsed_question.absence_type
            return "count_absences", minimized

        records = await self._tool_service.list_absences(
            employee_id=target_employee.employee_id,
            start_date=parsed_question.start_date,
            end_date=parsed_question.end_date,
            limit=20,
        )
        minimized = {
            "employee_id": target_employee.employee_id,
            "employee_display_name": target_employee.display_name,
            "period": {
                "start": parsed_question.start_date.isoformat(),
                "end": parsed_question.end_date.isoformat(),
            },
            "records": [record.model_dump(mode="json") for record in records],
        }
        return "list_absences", minimized

    async def _generate_answer(
        self,
        *,
        parsed_question: ParsedQuestion | None,
        status: RequestStatus,
        employee: Employee | None,
        result: dict,
        error_message: str | None,
        clarification_options: list[str],
        user_message: str,
    ) -> str:
        payload = AnswerGenerationPayload(
            request_status=status,
            intent=parsed_question.intent if parsed_question else None,
            employee_name=employee.display_name if employee else None,
            user_message=user_message,
            result=result,
            clarification_options=clarification_options,
            supported_capabilities=[
                "absence counts",
                "absence breakdowns by type",
                "absence lists",
            ],
            error_message=error_message,
        )
        return await self._llm_client.generate_answer(payload)

    def _resolve_sap_id(self, mock_id: str | None) -> str | None:
        """Translate a mock employee_id to the real SAP userId, falling back to the mock id."""
        if not mock_id:
            return None
        return self._sap_employee_id_map.get(mock_id, mock_id)

    def _should_route_to_general_chat(self, message: str) -> bool:
        lowered = message.lower()
        hr_or_data_markers = [
            r"\babsence\b",
            r"\babsences\b",
            r"\babsent\b",
            r"\bleave\b",
            r"\bleaves\b",
            r"\bvacation\b",
            r"\bvacations\b",
            r"\btime off\b",
            r"\bpto\b",
            r"\bsick leave\b",
            r"\bannual leave\b",
            r"\bmedical appointment\b",
            r"\bunpaid leave\b",
            r"\bdirect report\b",
            r"\bemployee\b",
            r"\bpayroll\b",
            r"\bsalary\b",
            r"\bbonus\b",
            r"\bcompensation\b",
            r"\bhr\b",
            r"\bsuccessfactors\b",
            r"\bsap\b",
        ]
        return not any(re.search(pattern, lowered, re.IGNORECASE) for pattern in hr_or_data_markers)

    async def _handle_leave_balance(self, intent, acting_sap_id, context, message, trace):
        sap_client = self._sap_client or getattr(self._sap_absence_agent, '_client', None)
        if not sap_client or not hasattr(sap_client, 'get_leave_balance'):
            answer = "Leave balance queries are only available when connected to SAP SuccessFactors."
            return answer, "unsupported", {}

        user_id = acting_sap_id
        if intent.employee_reference == "specific_employee" and intent.employee_name:
            try:
                resolved = await sap_client.resolve_user_id_by_name(intent.employee_name)
                if resolved:
                    user_id = resolved
            except Exception:
                pass

        self._record_step(trace, "sap_leave_balance", "running", "Fetching leave balance from EmpTimeAccountBalance.", {"user_id": user_id})
        try:
            balances = await sap_client.get_leave_balance(user_id=user_id)
        except Exception as exc:
            LOGGER.warning("[SAP] get_leave_balance failed: %s", exc)
            balances = []

        sap_result = {"user_id": user_id, "display_name": context.user_display_name, "balances": balances}
        self._record_step(trace, "sap_leave_balance", "completed", "Leave balance fetched.", {"count": len(balances)})

        answer = await self._generate_structured_answer(message, intent.model_dump(), sap_result)
        return answer, "success", sap_result

    async def _handle_approval_status(self, intent, acting_sap_id, context, message, trace):
        sap_client = self._sap_client or getattr(self._sap_absence_agent, '_client', None)
        if not sap_client or not hasattr(sap_client, 'get_pending_leave_requests'):
            answer = "Approval status queries are only available when connected to SAP SuccessFactors."
            return answer, "unsupported", {}

        user_id = acting_sap_id
        if intent.employee_reference == "specific_employee" and intent.employee_name:
            try:
                resolved = await sap_client.resolve_user_id_by_name(intent.employee_name)
                if resolved:
                    user_id = resolved
            except Exception:
                pass

        self._record_step(trace, "sap_approval_status", "running", "Fetching pending leave requests.", {"user_id": user_id})
        try:
            requests = await sap_client.get_pending_leave_requests(user_id=user_id)
        except Exception as exc:
            LOGGER.warning("[SAP] get_pending_leave_requests failed: %s", exc)
            requests = []

        display_name = intent.employee_name.title() if (intent.employee_reference == "specific_employee" and intent.employee_name) else context.user_display_name
        sap_result = {"user_id": user_id, "display_name": display_name, "pending_requests": requests}
        self._record_step(trace, "sap_approval_status", "completed", "Pending requests fetched.", {"count": len(requests)})

        answer = await self._generate_structured_answer(message, intent.model_dump(), sap_result)
        return answer, "success", sap_result

    async def _handle_absence_query(self, intent, acting_sap_id, context, message, trace):
        """Route absence_history, upcoming_absences, team_absences to the existing SapAbsenceAgent."""
        if self._sap_absence_agent is None:
            return "Absence queries are not available.", "unsupported", {}

        if self._settings.connector_backend == "successfactors":
            local_name_to_id = {
                e.display_name.lower(): self._sap_employee_id_map.get(e.employee_id, e.employee_id)
                for e in MOCK_EMPLOYEES
            }
        else:
            local_name_to_id = {e.display_name.lower(): e.employee_id for e in MOCK_EMPLOYEES}

        if context.user_role == "hr_admin" and self._sap_all_user_ids:
            effective_allowed_ids = self._sap_all_user_ids
        else:
            effective_allowed_ids = [self._resolve_sap_id(eid) for eid in context.allowed_employee_ids] or None

        self._record_step(trace, "sap_absence_agent", "running", f"Delegating {intent.intent} to SapAbsenceAgent.")
        result = await self._sap_absence_agent.handle(
            message,
            step_recorder=lambda name, step_status, detail, data=None: self._record_step(trace, name, step_status, detail, data),
            acting_sap_user_id=acting_sap_id,
            acting_user_display_name=context.user_display_name,
            allowed_employee_ids=effective_allowed_ids,
            local_name_to_id=local_name_to_id,
            all_sap_user_ids=self._sap_all_user_ids or None,
        )

        if not result.handled:
            return "I could not retrieve the absence data. Please try rephrasing your question.", "unavailable", {}

        sap_result = self._minimize_sap_absence_result(result)
        self._record_step(trace, "sap_absence_agent", "completed" if result.status == "success" else result.status,
                          "SapAbsenceAgent returned result.", {"status": result.status})

        if result.status == "success":
            # Apply approval_status_filter if the LLM extracted one
            status_filter = (intent.extracted_parameters or {}).get("approval_status_filter")
            if status_filter and isinstance(sap_result.get("absences"), list):
                filter_upper = status_filter.upper()
                sap_result["absences"] = [
                    a for a in sap_result["absences"]
                    if (a.get("approval_status") or "").upper() == filter_upper
                ]
                sap_result["absence_count"] = len(sap_result["absences"])
                sap_result["applied_filter"] = status_filter

            answer = await self._generate_structured_answer(message, intent.model_dump(), sap_result)
            return answer, "success", sap_result
        else:
            return self._sap_result_to_answer(result), self._sap_result_to_request_status(result), sap_result

    async def _handle_create_absence_request(
        self, intent, acting_sap_id, context, message, trace,
        sap_record_key: str | None = None,
        pending_attachments: dict | None = None,
    ):
        sap_client = self._sap_client or getattr(self._sap_absence_agent, "_client", None)
        if not sap_client or not hasattr(sap_client, "post_time_off_request"):
            return "Creating absence requests is only available when connected to SAP SuccessFactors.", "unsupported", {}

        user_id = acting_sap_id
        if intent.employee_reference == "specific_employee" and intent.employee_name:
            try:
                resolved = await sap_client.resolve_user_id_by_name(intent.employee_name)
                if resolved:
                    user_id = resolved
            except Exception:
                pass

        if not user_id:
            return (
                "I need your SAP user ID to submit a leave request. Please ask your administrator to configure SAP_ACTING_USER_ID.",
                "clarification_required",
                {},
            )

        start_date = intent.date_range.get("start")
        end_date = intent.date_range.get("end")

        if not start_date or not end_date:
            return (
                "Please specify the start and end dates for your leave request, e.g. 'I want to request leave from June 5 to June 7'.",
                "clarification_required",
                {},
            )

        try:
            from datetime import date as _date
            _date.fromisoformat(start_date)
            _date.fromisoformat(end_date)
        except (ValueError, TypeError):
            return (
                f"The dates '{start_date}' / '{end_date}' are not valid. Please use a clear format like 'June 5 to June 7'.",
                "clarification_required",
                {},
            )

        time_type_code, time_type_name = _resolve_time_type(intent.absence_type)

        # LLM sometimes doesn't populate absence_type — fall back to scanning the raw message
        if not time_type_code:
            time_type_code, time_type_name = _resolve_time_type(message)

        if not time_type_code:
            try:
                available = await sap_client.get_time_types()
            except Exception:
                available = []
            if available:
                type_list = "\n".join(f"• {t['name']} (code: {t['code']})" for t in available[:10])
                return (
                    f"What type of leave would you like to request? Available types:\n{type_list}",
                    "clarification_required",
                    {"available_types": available},
                )
            return (
                "Please specify the type of leave (e.g. annual leave, sickness, unpaid leave, maternity leave).",
                "clarification_required",
                {},
            )

        # Use the upload record key as externalCode so the SAP attachment can link to this time record
        pre_external_code = sap_record_key if sap_record_key else None
        has_attachment = bool(sap_record_key and pending_attachments and sap_record_key in (pending_attachments or {}))

        self._record_step(trace, "sap_time_off_request", "running", "Submitting time off request to SAP SuccessFactors.", {
            "user_id": user_id, "time_type": time_type_code, "start_date": start_date, "end_date": end_date,
            "has_attachment": has_attachment,
        })

        # When an attachment is provided: upload it first, then create EmployeeTime.
        # When no attachment: try to create EmployeeTime — if SAP rejects with "needs attachment", surface that to the user.
        attachment_id = None
        if has_attachment and pending_attachments and sap_record_key:
            att = pending_attachments[sap_record_key]
            self._record_step(trace, "sap_attachment_upload", "running", "Uploading attachment to SAP.", {"file_name": att.get("file_name")})
            # Upload as the authenticated service account (acting_sap_id / token holder).
            # SAP validates that the attachment's userId matches the token user, not the target employee.
            upload_user_id = acting_sap_id or user_id
            try:
                attachment_id = await sap_client.upload_attachment(
                    file_bytes=att["file_bytes"],
                    file_name=att["file_name"],
                    mime_type=att["mime_type"],
                    user_id=upload_user_id,
                    document_entity_id=pre_external_code or f"CHAT_{user_id}",
                )
                self._record_step(trace, "sap_attachment_upload", "completed", "Attachment uploaded.", {"attachment_id": attachment_id})
            except ConnectorUnavailableError as exc:
                self._record_step(trace, "sap_attachment_upload", "error", str(exc))
                LOGGER.warning("[SAP] Attachment upload failed: %s", exc)
                return (
                    f"The document upload to SAP failed: {exc}. Please try uploading again or contact your HR administrator.",
                    "error",
                    {"error": str(exc)},
                )

        try:
            response = await sap_client.post_time_off_request(
                user_id=user_id,
                time_type=time_type_code,
                start_date=start_date,
                end_date=end_date,
                external_code=pre_external_code,
                attachment_id=attachment_id,
            )
            final_code = (
                response.get("d", {}).get("externalCode")
                or response.get("externalCode")
                or pre_external_code
            )

            sap_result = {
                "user_id": user_id,
                "time_type": time_type_code,
                "time_type_name": time_type_name,
                "start_date": start_date,
                "end_date": end_date,
                "external_code": final_code,
                "attachment_id": attachment_id,
                "status": "submitted",
            }
            self._record_step(trace, "sap_time_off_request", "completed", "Time off request submitted.", sap_result)
            # Clean up consumed pending attachment
            if sap_record_key and pending_attachments and sap_record_key in pending_attachments:
                del pending_attachments[sap_record_key]
            answer = await self._generate_structured_answer(message, intent.model_dump(), sap_result)
            return answer, "success", sap_result
        except ConnectorUnavailableError as exc:
            err_str = str(exc)
            err_lower = err_str.lower()
            needs_doc = "attachment" in err_lower or "justificatif" in err_lower or "document" in err_lower
            if needs_doc and not has_attachment:
                sap_result = {
                    "status": "needs_attachment",
                    "needs_attachment": True,
                    "pending_time_type": time_type_code,
                    "pending_time_type_name": time_type_name,
                    "pending_start_date": start_date,
                    "pending_end_date": end_date,
                    "user_id": user_id,
                    "error": err_str,
                }
                self._record_step(trace, "sap_time_off_request", "needs_attachment", err_str)
                answer = (
                    f"This leave type (**{time_type_name}**) requires a supporting document. "
                    f"Please upload an attachment (e.g. marriage certificate, medical note) "
                    f"and I will re-submit your request automatically."
                )
                return answer, "clarification_required", sap_result
            self._record_step(trace, "sap_time_off_request", "error", err_str)
            return err_str, "error", {}

    async def _handle_schedule_query(self, intent, acting_sap_id, context, message, trace):
        client = self._sap_client or getattr(self._sap_absence_agent, "_client", None)
        if not client:
            return "Schedule and holiday queries are not available in this mode.", "unsupported", {}

        # Rebuild agent with the resolved client each time (handles both mock and SAP modes)
        agent = ScheduleAgent(client=client)

        # Resolve specific employee if named
        user_id = acting_sap_id
        employee_name = intent.employee_name if intent.employee_reference == "specific_employee" else None
        employee_found = True
        if intent.employee_reference == "specific_employee" and intent.employee_name:
            try:
                resolved = await client.resolve_user_id_by_name(intent.employee_name)
                if resolved:
                    user_id = resolved
                    employee_found = True
                else:
                    employee_found = False
            except Exception:
                employee_found = False

        self._record_step(trace, "schedule_agent", "running",
                          f"Delegating {intent.intent} to ScheduleAgent.", {"user_id": user_id})
        # Map LLM intent to ScheduleAgent sub-intent so regex typo issues don't block it
        schedule_intent_override = (
            "holiday" if intent.intent == "holiday_query" else
            "work_schedule" if intent.intent == "work_schedule_query" else None
        )
        result = await agent.handle(
            message,
            acting_sap_user_id=user_id,
            step_recorder=lambda name, s, detail, data=None: self._record_step(trace, name, s, detail, data),
            employee_name=employee_name,
            employee_found=employee_found,
            intent_override=schedule_intent_override,
        )

        if not result.handled:
            return "I could not retrieve schedule data. Please try rephrasing.", "unavailable", {}

        if result.status == "success":
            sap_result = {
                "intent": result.intent,
                "holidays": result.holidays,
                "work_schedule": result.work_schedule,
                "date_range": result.date_range,
                "employee_name": employee_name,
                "employee_found": employee_found,
            }
            self._record_step(trace, "schedule_agent", "completed", "ScheduleAgent returned result.",
                              {"holidays": len(result.holidays), "has_schedule": result.work_schedule is not None})
            answer = result.summary_text or "No data found for that request."
            return answer, "success", sap_result

        if result.status == "needs_clarification":
            return result.message, "clarification_required", {}

        return result.message or "Could not retrieve the requested data.", "unavailable", {}

    async def _handle_general_chat_intent(self, message, context, trace):
        self._record_step(trace, "general_chat", "running", "Handling as general conversation.")
        payload = AnswerGenerationPayload(
            request_status="success",
            intent="general_chat",
            user_message=message,
            result={"mode": "general_chat"},
            supported_capabilities=["leave balance", "upcoming absences", "absence history", "approval status", "team absences"],
        )
        answer = await self._llm_client.generate_answer(payload)
        return answer, "success", {}

    async def _generate_structured_answer(self, user_message: str, intent_json: dict, sap_result: dict) -> str:
        """Step 2 LLM call: generate a natural-language answer from the SAP result."""
        if hasattr(self._llm_client, 'generate_structured_answer'):
            try:
                return await self._llm_client.generate_structured_answer(user_message, intent_json, sap_result)
            except Exception:
                pass
        # Fallback to existing generate_answer
        payload = AnswerGenerationPayload(
            request_status="success",
            intent=intent_json.get("intent"),
            user_message=user_message,
            result=sap_result,
        )
        return await self._llm_client.generate_answer(payload)

    def _record_step(
        self,
        trace: ToolTrace,
        name: str,
        status: str,
        detail: str,
        data: dict | None = None,
    ) -> None:
        trace.process_steps.append(
            {
                "step": name,
                "status": status,
                "detail": detail,
                "data": data or {},
                "timestamp": utc_now().isoformat(),
            }
        )

    def _sap_result_to_request_status(self, result: SapAbsenceResult) -> RequestStatus:
        if result.status == "success":
            return "success"
        if result.status == "needs_clarification":
            return "clarification_required"
        if result.status == "error":
            return "unavailable"
        return "unsupported"

    def _sap_result_to_parsed_question(self, result: SapAbsenceResult) -> ParsedQuestion:
        if result.status == "success":
            employee_reference = "workforce" if result.employee is None else result.employee.get("name") or result.employee.get("userId")
            return ParsedQuestion(
                intent="absence_list",
                employee_reference=employee_reference,
                start_date=date.fromisoformat(result.date_range["startDate"]),
                end_date=date.fromisoformat(result.date_range["endDate"]),
                needs_clarification=False,
            )
        if result.status == "needs_clarification":
            return ParsedQuestion(
                intent="absence_list",
                needs_clarification=True,
                clarification_reason=result.message,
            )
        return ParsedQuestion(intent="unsupported", needs_clarification=False)

    def _sap_result_to_answer(self, result: SapAbsenceResult) -> str:
        if result.status == "success":
            return result.summary_text
        if result.status == "needs_clarification":
            return result.message
        if result.status == "error":
            return result.message
        return "This message is not an SAP absence request."

    def _dept_overlap_result_to_request_status(self, result: SapDepartmentOverlapResult) -> RequestStatus:
        if result.status == "success":
            return "success"
        if result.status == "needs_clarification":
            return "clarification_required"
        if result.status == "error":
            return "unavailable"
        return "unsupported"

    def _dept_overlap_result_to_parsed_question(self, result: SapDepartmentOverlapResult) -> ParsedQuestion:
        if result.status == "success":
            employee_reference = (
                result.target_employee.get("name") or result.target_employee.get("userId")
                if result.target_employee else None
            )
            return ParsedQuestion(
                intent="absence_list",
                employee_reference=employee_reference,
                start_date=date.fromisoformat(result.date_range["startDate"]),
                end_date=date.fromisoformat(result.date_range["endDate"]),
                needs_clarification=False,
            )
        if result.status == "needs_clarification":
            return ParsedQuestion(
                intent="absence_list",
                needs_clarification=True,
                clarification_reason=result.message,
            )
        return ParsedQuestion(intent="unsupported", needs_clarification=False)

    def _dept_overlap_result_to_answer(self, result: SapDepartmentOverlapResult) -> str:
        if result.status == "success":
            return result.summary_text
        if result.status == "needs_clarification":
            return result.message
        if result.status == "error":
            return result.message
        return "This message is not a department overlap request."

    def _minimize_dept_overlap_result(self, result: SapDepartmentOverlapResult) -> dict:
        minimized = asdict(result) if is_dataclass(result) else {}
        if "absences" in minimized:
            minimized["absence_count"] = len(minimized["absences"])
            minimized["absences"] = [
                {
                    "user_id": item.get("user_id"),
                    "start_date": item.get("start_date"),
                    "end_date": item.get("end_date"),
                    "absence_type": item.get("absence_type"),
                    "approval_status": item.get("approval_status"),
                    "quantity_in_days": item.get("quantity_in_days"),
                    "quantity_in_hours": item.get("quantity_in_hours"),
                    "external_code": item.get("external_code"),
                }
                for item in minimized["absences"]
                if isinstance(item, dict)
            ]
        return minimized

    def _minimize_sap_absence_result(self, result: SapAbsenceResult) -> dict:
        if is_dataclass(result):
            minimized = asdict(result)
        else:
            minimized = {}
        if "absences" in minimized:
            minimized["absence_count"] = len(minimized["absences"])
            minimized["absences"] = [
                {
                    "user_id": item.get("user_id"),
                    "start_date": item.get("start_date"),
                    "end_date": item.get("end_date"),
                    "absence_type": item.get("absence_type"),
                    "approval_status": item.get("approval_status"),
                    "quantity_in_days": item.get("quantity_in_days"),
                    "quantity_in_hours": item.get("quantity_in_hours"),
                    "external_code": item.get("external_code"),
                }
                for item in minimized["absences"]
                if isinstance(item, dict)
            ]
        return minimized

    async def _finalize(
        self,
        *,
        trace: ToolTrace,
        request_id: str,
        answer: str,
        parsed_question: ParsedQuestion | None,
        tool_name: str | None,
        target_employee: Employee | None,
        authorization_outcome: str,
        status: RequestStatus,
        started: float,
        message: str,
        context_user,
    ) -> ChatResponse:
        duration_ms = int((time.perf_counter() - started) * 1000)
        trace.completed_at = utc_now()
        trace.duration_ms = duration_ms
        trace.status = status
        trace.answer_metadata = {
            "answered_with_local_model": True,
            "llm_backend": self._llm_client.backend_name,
            "llm_model": trace.llm_model,
            "external_ai_calls": "none",
        }

        if context_user is not None:
            self._request_repository.finalize_request(
                request_id=request_id,
                parsed_intent=parsed_question.intent if parsed_question else None,
                tool_name=tool_name,
                target_employee_id=target_employee.employee_id if target_employee else None,
                authorization_outcome=authorization_outcome,
                status=status,
                duration_ms=duration_ms,
                answer=answer,
                trace=trace,
            )
            self._audit_service.record(
                request_id=request_id,
                acting_user=context_user.user_display_name,
                user_role=context_user.user_role,
                original_question=message,
                parsed_intent=parsed_question.intent if parsed_question else None,
                tool_called=tool_name,
                target_employee=target_employee.employee_id if target_employee else None,
                authorization_outcome=authorization_outcome,
                final_status=status,
                duration_ms=duration_ms,
                data_source=trace.data_source,
            )
        return ChatResponse(request_id=request_id, status=status, answer=answer, trace=trace)
