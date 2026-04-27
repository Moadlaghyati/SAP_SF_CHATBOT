from __future__ import annotations

import re
import time
from dataclasses import asdict, is_dataclass
from datetime import date
from uuid import uuid4

from app.agents.sap.absence_intent import detect_absence_intent
from app.agents.sap.absence_schemas import SapAbsenceResult
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
    ):
        self._settings = settings
        self._authorization_service = authorization_service
        self._tool_service = tool_service
        self._request_repository = request_repository
        self._audit_service = audit_service
        self._llm_client = llm_client
        self._sap_absence_agent = sap_absence_agent

    async def handle_message(self, message: str, user_id: str) -> ChatResponse:
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

            sap_absence_precheck = detect_absence_intent(message)
            self._record_step(
                trace,
                "absence_intent_precheck",
                "completed",
                "Checked whether the message explicitly asks for absence, leave, PTO, vacation, holiday, sick leave, or time-off data.",
                {
                    "should_handle": sap_absence_precheck.should_handle,
                    "confidence": sap_absence_precheck.confidence,
                    "reason": sap_absence_precheck.reason,
                    "active_connector": self._tool_service.connector_backend,
                },
            )
            if self._sap_absence_agent is not None and sap_absence_precheck.should_handle:
                self._record_step(trace, "sap_absence_agent", "running", "Delegated request to the dedicated SAP Absence Agent.")
                result = await self._sap_absence_agent.handle(
                    message,
                    step_recorder=lambda name, step_status, detail, data=None: self._record_step(
                        trace, name, step_status, detail, data
                    ),
                )
                if result.handled:
                    self._record_step(
                        trace,
                        "sap_absence_agent",
                        "completed" if result.status == "success" else result.status,
                        "SAP Absence Agent returned a structured result.",
                        {"result_status": result.status},
                    )
                    parsed_question = self._sap_result_to_parsed_question(result)
                    trace.detected_intent = "sap_absences"
                    trace.parsed_request = {
                        "intent": asdict(sap_absence_precheck),
                        "agent_result_status": result.status,
                    }
                    trace.tool_name = "sap_absence_agent"
                    trace.authorization_outcome = "not_applicable"
                    trace.status = self._sap_result_to_request_status(result)
                    trace.minimized_result = self._minimize_sap_absence_result(result)
                    status = trace.status  # type: ignore[assignment]
                    authorization_outcome = trace.authorization_outcome
                    answer = self._sap_result_to_answer(result)
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

            if self._should_route_to_general_chat(message):
                self._record_step(trace, "routing", "completed", "Routed to general chat before HR data extraction.")
                parsed_question = ParsedQuestion(intent="general_chat", needs_clarification=False)
                trace.detected_intent = parsed_question.intent
                trace.parsed_request = parsed_question.model_dump(mode="json")
                status = "success"
                authorization_outcome = "not_applicable"
                trace.authorization_outcome = authorization_outcome
                trace.status = status
                trace.minimized_result = {"mode": "general_chat", "routing": "heuristic_precheck"}
                answer = await self._generate_answer(
                    parsed_question=parsed_question,
                    status=status,
                    employee=None,
                    result={"mode": "general_chat", "routing": "heuristic_precheck"},
                    error_message=None,
                    clarification_options=[],
                    user_message=message,
                )
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

            self._record_step(trace, "llm_extract_request", "running", "Local model is extracting intent, employee reference, and dates.")
            parsed_question = await self._llm_client.extract_question(
                message, current_date=self._settings.demo_reference_date
            )
            self._record_step(
                trace,
                "llm_extract_request",
                "completed",
                "Local model returned structured request fields.",
                parsed_question.model_dump(mode="json"),
            )
            trace.detected_intent = parsed_question.intent
            trace.parsed_request = parsed_question.model_dump(mode="json")

            if parsed_question.intent == "unsupported":
                self._record_step(trace, "routing", "stopped", "Request is outside the supported assistant capabilities.")
                status = "unsupported"
                authorization_outcome = "not_applicable"
                trace.authorization_outcome = authorization_outcome
                trace.status = status
                trace.minimized_result = {"mode": "unsupported_demo_scope"}
                answer = await self._generate_answer(
                    parsed_question=parsed_question,
                    status=status,
                    employee=None,
                    result={"mode": "unsupported_demo_scope"},
                    error_message=None,
                    clarification_options=[],
                    user_message=message,
                )
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

            if parsed_question.intent == "general_chat":
                self._record_step(trace, "routing", "completed", "Routed to general chat after local model extraction.")
                status = "success"
                authorization_outcome = "not_applicable"
                trace.authorization_outcome = authorization_outcome
                trace.status = status
                trace.minimized_result = {"mode": "general_chat"}
                answer = await self._generate_answer(
                    parsed_question=parsed_question,
                    status=status,
                    employee=None,
                    result={"mode": "general_chat"},
                    error_message=None,
                    clarification_options=[],
                    user_message=message,
                )
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

            if parsed_question.needs_clarification:
                self._record_step(trace, "clarification", "stopped", parsed_question.clarification_reason or "More information is required.")
                status = "clarification_required"
                authorization_outcome = "needs_clarification"
                trace.authorization_outcome = authorization_outcome
                trace.authorization_reason = parsed_question.clarification_reason
                trace.status = status
                answer = await self._generate_answer(
                    parsed_question=parsed_question,
                    status=status,
                    employee=None,
                    result={},
                    error_message=parsed_question.clarification_reason,
                    clarification_options=[],
                    user_message=message,
                )
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

            self._record_step(
                trace,
                "resolve_employee",
                "running",
                "Resolving the extracted employee reference against the active connector.",
                {"reference": parsed_question.employee_reference},
            )
            raw_matches = await self._tool_service.resolve_employee(
                parsed_question.employee_reference or "", context
            )
            trace.tool_name = "resolve_employee"
            trace.tool_arguments = {"reference": parsed_question.employee_reference}
            if not raw_matches:
                self._record_step(
                    trace,
                    "resolve_employee",
                    "stopped",
                    "No employee matched the extracted reference in the active data source.",
                    {
                        "reference": parsed_question.employee_reference,
                        "data_source": self._tool_service.connector_backend,
                    },
                )
                status = "not_found"
                authorization_outcome = "not_found"
                trace.authorization_outcome = authorization_outcome
                trace.authorization_reason = "No employee matched the provided reference."
                trace.status = status
                answer = await self._generate_answer(
                    parsed_question=parsed_question,
                    status=status,
                    employee=None,
                    result={},
                    error_message="I could not find a matching employee in the demo dataset.",
                    clarification_options=[],
                    user_message=message,
                )
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

            authorized_matches = self._authorization_service.filter_authorized_matches(context, raw_matches)
            self._record_step(
                trace,
                "authorization",
                "completed" if authorized_matches else "stopped",
                "Filtered resolved employees by the acting user's permissions.",
                {
                    "resolved_matches": len(raw_matches),
                    "authorized_matches": len(authorized_matches),
                },
            )
            if not authorized_matches:
                status = "forbidden"
                authorization_outcome = "forbidden"
                trace.authorization_outcome = authorization_outcome
                trace.authorization_reason = "The requester is not permitted to view the resolved employee."
                trace.status = status
                answer = await self._generate_answer(
                    parsed_question=parsed_question,
                    status=status,
                    employee=None,
                    result={},
                    error_message="You do not have permission to view that employee's absence data.",
                    clarification_options=[],
                    user_message=message,
                )
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

            if len(authorized_matches) > 1:
                self._record_step(trace, "ambiguity_check", "stopped", "Multiple authorized employees matched the request.")
                status = "clarification_required"
                authorization_outcome = "ambiguous"
                trace.authorization_outcome = authorization_outcome
                trace.authorization_reason = "Multiple authorized employees matched the reference."
                trace.status = status
                answer = await self._generate_answer(
                    parsed_question=parsed_question,
                    status=status,
                    employee=None,
                    result={},
                    error_message="I found multiple matching employees.",
                    clarification_options=[employee.display_name for employee in authorized_matches],
                    user_message=message,
                )
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

            target_employee = authorized_matches[0]
            self._record_step(
                trace,
                "target_employee",
                "completed",
                "Resolved one authorized target employee.",
                {"employee_id": target_employee.employee_id, "display_name": target_employee.display_name},
            )
            authorization_outcome = "authorized"
            trace.authorization_outcome = authorization_outcome
            trace.target_employee_id = target_employee.employee_id
            trace.target_employee_display_name = target_employee.display_name

            self._record_step(trace, "tool_execution", "running", "Running the approved absence tool.")
            tool_name, result = await self._run_tool(parsed_question, target_employee)
            self._record_step(trace, "tool_execution", "completed", "Absence tool returned a minimized result.", {"tool_name": tool_name})
            status = "success"
            trace.tool_name = tool_name
            trace.tool_arguments = {
                "employee_id": target_employee.employee_id,
                "start_date": parsed_question.start_date.isoformat() if parsed_question.start_date else None,
                "end_date": parsed_question.end_date.isoformat() if parsed_question.end_date else None,
                "absence_type": parsed_question.absence_type,
            }
            trace.minimized_result = result
            trace.status = status
            answer = await self._generate_answer(
                parsed_question=parsed_question,
                status=status,
                employee=target_employee,
                result=result,
                error_message=None,
                clarification_options=[],
                user_message=message,
            )
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
