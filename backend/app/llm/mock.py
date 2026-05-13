from __future__ import annotations

import ast
import calendar
import re
from datetime import date, timedelta

from app.llm.base import LocalLLMClient
from app.schemas.domain import LocalModelSummary
from app.schemas.llm import AbsenceExtractionResult, AnswerGenerationPayload, ParsedQuestion


class MockLocalLLMClient(LocalLLMClient):
    backend_name = "mock"

    async def extract_question(self, question: str, current_date: date) -> ParsedQuestion:
        text = question.strip()
        lowered = text.lower()

        if any(keyword in lowered for keyword in ["payroll", "salary", "bonus", "compensation"]):
            return ParsedQuestion(intent="unsupported", needs_clarification=False)

        if not self._looks_like_absence_query(lowered):
            return ParsedQuestion(
                intent="general_chat",
                needs_clarification=False,
            )

        intent = "absence_count"
        if "breakdown" in lowered or "by type" in lowered:
            intent = "absence_breakdown"
        elif "absence" in lowered and (lowered.startswith("list") or "list " in lowered):
            intent = "absence_list"

        absence_type = None
        for candidate in ["sick leave", "sick leaves", "annual leave", "medical appointment", "unpaid leave"]:
            if candidate in lowered:
                absence_type = candidate.replace("sick leaves", "Sick Leave").title()
                if absence_type == "Sick Leave":
                    absence_type = "Sick Leave"
                break

        start_date, end_date = self._extract_dates(text, current_date)
        employee_reference = self._extract_employee_reference(text)

        needs_clarification = employee_reference is None or start_date is None or end_date is None
        clarification_reason = None
        if employee_reference is None:
            clarification_reason = "Please specify which employee you mean."
        elif start_date is None or end_date is None:
            clarification_reason = "Please provide a clear date range."

        return ParsedQuestion(
            intent=intent,  # type: ignore[arg-type]
            employee_reference=employee_reference,
            start_date=start_date,
            end_date=end_date,
            absence_type=absence_type,
            needs_clarification=needs_clarification,
            clarification_reason=clarification_reason,
        )

    async def extract_absence_params(self, question: str, current_date: date) -> AbsenceExtractionResult:
        from app.agents.sap.absence_extraction import extract_absence_retrieval_params
        params = extract_absence_retrieval_params(question, current_date=current_date)
        return AbsenceExtractionResult(
            scope=params.scope,
            employee_name=params.employee_name,
            employee_name_b=params.employee_name_b,
            user_id=params.user_id,
            start_date=params.start_date,
            end_date=params.end_date,
            needs_clarification=bool(params.missing_required_fields),
            clarification_message=params.clarification_message,
        )

    async def generate_answer(self, payload: AnswerGenerationPayload) -> str:
        status = payload.request_status
        result = payload.result

        if payload.intent == "general_chat":
            return self._generate_general_chat_reply(payload.user_message or "")

        if status == "forbidden":
            return payload.error_message or "You do not have permission to view that employee's absence data."
        if status == "clarification_required":
            options = payload.clarification_options
            if options:
                return "I found multiple matching employees. Please clarify which one you mean: " + ", ".join(options) + "."
            return payload.error_message or "I need a clearer employee name or date range to answer that safely."
        if status == "not_found":
            return payload.error_message or "I could not find a matching employee in the demo dataset."
        if status == "unsupported":
            capabilities = self._render_supported_capabilities(payload.supported_capabilities)
            return (
                "I cannot help with that request in this demo yet. "
                f"I can help with {capabilities}."
            )
        if status == "invalid_input":
            return payload.error_message or "I could not safely interpret that request. Please include an employee and date range."
        if status == "unavailable":
            return payload.error_message or "The local model or connector is unavailable right now."
        if status != "success":
            return payload.error_message or "The request could not be completed."

        intent = payload.intent
        employee_name = payload.employee_name or result.get("employee_display_name") or "the employee"

        if intent == "absence_list":
            records = result.get("records", [])
            if not records:
                return (
                    f"{employee_name} has no recorded absences between "
                    f"{result['period']['start']} and {result['period']['end']}."
                )
            rendered = "; ".join(
                f"{record['absence_type']} from {record['start_date']} to {record['end_date']} ({record['days']} days)"
                for record in records
            )
            return (
                f"{employee_name} has {len(records)} absence record(s) between "
                f"{result['period']['start']} and {result['period']['end']}: {rendered}."
            )

        if intent == "absence_breakdown":
            breakdown = ", ".join(
                f"{item['type']}: {item['count']} absence(s), {item['days']} day(s)"
                for item in result.get("by_type", [])
            )
            return (
                f"{employee_name} had {result['absence_count']} absence(s) totaling {result['absence_days']} day(s) "
                f"between {result['period']['start']} and {result['period']['end']}. Breakdown by type: {breakdown}."
            )

        if result.get("absence_type"):
            return (
                f"{employee_name} had {result['absence_count']} {result['absence_type']} absence(s) "
                f"between {result['period']['start']} and {result['period']['end']}."
            )

        return (
            f"{employee_name} had {result['absence_count']} absence(s) totaling {result['absence_days']} day(s) "
            f"between {result['period']['start']} and {result['period']['end']}."
        )

    async def analyze_intent(self, question: str, current_date: date, acting_user_display_name: str | None = None) -> "StructuredIntent":
        from app.schemas.llm import StructuredIntent
        lowered = question.lower()

        # Determine intent
        if any(k in lowered for k in ["balance", "days left", "remaining", "how many days do i have"]):
            intent = "leave_balance"
        elif any(k in lowered for k in ["upcoming", "next week", "tomorrow", "who is absent", "who will be absent"]):
            intent = "upcoming_absences"
        elif any(k in lowered for k in ["history", "last month", "last year", "past absences"]):
            intent = "absence_history"
        elif any(k in lowered for k in ["approved", "pending", "approval", "status of my"]):
            intent = "approval_status"
        elif any(k in lowered for k in ["request", "apply for", "submit", "book leave"]):
            intent = "create_absence_request"
        elif any(k in lowered for k in ["cancel", "withdraw"]):
            intent = "cancel_absence_request"
        elif any(k in lowered for k in ["team", "department", "my direct reports", "my team"]):
            intent = "team_absences"
        elif any(k in lowered for k in [
            "holiday", "holidays", "public holiday", "jour férié", "jours fériés",
            "férié", "ferie", "eid", "ramadan", "throne day", "labour day",
            "independence", "new year", "mawlid", "national day", "bank holiday",
            "marche verte", "aïd", "aid al", "eid al", "hijri",
        ]):
            intent = "holiday_query"
        elif any(k in lowered for k in [
            "work schedule", "working hours", "work hours", "horaire",
            "horaires de travail", "schedule", "working days", "what time",
            "start time", "end time", "hours per week", "days per week",
        ]):
            intent = "work_schedule_query"
        else:
            intent = "unknown"

        # Determine employee_reference
        if re.search(r'\b(my|i |i\'m|me\b|myself)\b', lowered):
            employee_reference = "current_user"
        elif any(k in lowered for k in ["team", "department", "direct reports"]):
            employee_reference = "manager_team"
        else:
            employee_reference = "unknown"

        return StructuredIntent(
            intent=intent,
            employee_reference=employee_reference,
            clarification_needed=False,
        )

    async def generate_structured_answer(self, user_message: str, intent_json: dict, sap_result: dict) -> str:
        intent = intent_json.get("intent", "unknown")

        if intent == "holiday_query":
            holidays = sap_result.get("holidays", [])
            date_range = sap_result.get("date_range", {})
            start = date_range.get("startDate", "")
            end = date_range.get("endDate", "")
            if not holidays:
                return f"No public holidays found between {start} and {end}."
            lines = [f"Here are the **{len(holidays)}** public holiday(s) between {start} and {end}:\n"]
            for h in holidays:
                lines.append(f"• **{h['date']}** — {h['name']}")
            return "\n".join(lines)

        if intent == "work_schedule_query":
            ws = sap_result.get("work_schedule")
            if not ws:
                return "No work schedule found for this employee."
            name = ws.get("employee_display_name", ws.get("employee_id", "Employee"))
            sched = ws.get("schedule_name", "Standard")
            hours = ws.get("hours_per_week", 40)
            days = ws.get("days_per_week", 5)
            work_days = ws.get("work_days", [])
            lines = [f"**{name}** follows the **{sched}** schedule:"]
            lines.append(f"• {days} working days/week · {hours} hours/week")
            if work_days:
                for d in work_days:
                    lines.append(f"• {d['day']}: {d['start']} – {d['end']} ({d['hours']}h)")
            return "\n".join(lines)

        if not sap_result:
            return "No matching information was found."

        # Absence-related fallback
        absences = sap_result.get("absences", [])
        if absences:
            return (
                f"Found **{len(absences)}** absence record(s). "
                + "; ".join(
                    f"{a.get('absence_type','?')} ({a.get('start_date','?')} – {a.get('end_date','?')})"
                    for a in absences[:5]
                )
            )
        return sap_result.get("summary", sap_result.get("summary_text", "Request completed successfully."))

    async def health_check(self) -> tuple[bool, str]:
        return True, "Mock local LLM is ready."

    async def list_available_models(self) -> list[LocalModelSummary]:
        return [LocalModelSummary(name="mock")]

    def _looks_like_absence_query(self, lowered: str) -> bool:
        absence_patterns = [
            r"\babsence\b",
            r"\babsences\b",
            r"\bleave\b",
            r"\bleaves\b",
            r"\bsick leave\b",
            r"\bannual leave\b",
            r"\bmedical appointment\b",
            r"\bunpaid leave\b",
            r"\bdirect report\b",
            r"\bbreakdown by type\b",
        ]
        return any(re.search(pattern, lowered, re.IGNORECASE) for pattern in absence_patterns)

    def _generate_general_chat_reply(self, user_message: str) -> str:
        lowered = user_message.lower().strip()
        arithmetic_result = self._try_evaluate_arithmetic(user_message)
        if arithmetic_result is not None:
            return f"The answer is {arithmetic_result}."

        if any(
            re.search(pattern, lowered, re.IGNORECASE)
            for pattern in [r"\bhello\b", r"\bhi\b", r"\bhey\b", r"\bgood morning\b", r"\bgood afternoon\b", r"\bgood evening\b"]
        ):
            return (
                "Hello. I am your local HR assistant demo. "
                "I can answer absence-related questions, show breakdowns by type, list absences, and explain what this demo can do."
            )

        if re.search(r"\bwhat can you do\b", lowered, re.IGNORECASE) or re.search(r"\bhelp\b", lowered, re.IGNORECASE):
            return (
                "I can help with absence counts, absence breakdowns by type, and absence lists for authorized employees in the demo dataset. "
                "For example, ask: How many absences did Sara Bennani have between 2026-01-01 and 2026-03-31?"
            )

        if re.search(r"\bthank", lowered, re.IGNORECASE):
            return "You are welcome. If you want, ask me about an employee's absences and I will walk through it."

        return (
            "I am here and responding locally. "
            "You can ask me general questions, chat naturally, or ask an absence question about an authorized demo employee."
        )

    def _render_supported_capabilities(self, supported_capabilities: list[str]) -> str:
        if not supported_capabilities:
            return "absence counts, absence breakdowns, and absence lists"
        if len(supported_capabilities) == 1:
            return supported_capabilities[0]
        return ", ".join(supported_capabilities[:-1]) + f", and {supported_capabilities[-1]}"

    def _try_evaluate_arithmetic(self, user_message: str) -> str | None:
        normalized = user_message.lower().strip()
        normalized = re.sub(r"^(how much is|what is|calculate)\s+", "", normalized)
        normalized = normalized.rstrip(" ?.")
        if not re.fullmatch(r"[0-9\.\+\-\*\/\(\)\s]+", normalized):
            return None

        try:
            expression = ast.parse(normalized, mode="eval")
            value = self._evaluate_ast(expression.body)
        except (SyntaxError, ValueError, ZeroDivisionError):
            return None

        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    def _evaluate_ast(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left = self._evaluate_ast(node.left)
            right = self._evaluate_ast(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            return left / right
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self._evaluate_ast(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        raise ValueError("Unsupported arithmetic expression.")

    def _extract_employee_reference(self, text: str) -> str | None:
        normalized_text = text.replace("’", "'")
        patterns = [
            r"how many absences did (.+?) have",
            r"how many sick leaves did (.+?) have",
            r"how much leaves do (.+?) had",
            r"how much leaves did (.+?) have",
            r"how many leaves did (.+?) have",
            r"list (.+?)'s absences",
            r"list (.+?) absences",
            r"show the absence breakdown by type for (.+?) in",
            r"show .* for (.+?) between",
            r"for (.+?)\s+(?:this\s+month|this\s+mounth|\(\d{1,2}[/\-]\d{4}\))",
            r"for (.+?) in [A-Z]",
        ]
        lowered = normalized_text.lower()
        if "my direct report" in lowered:
            direct_report_match = re.search(
                r"my direct report ([A-Za-z ]+?)(?: have| between| in| last month|$)",
                normalized_text,
                re.IGNORECASE,
            )
            if direct_report_match:
                return direct_report_match.group(1).strip()

        for pattern in patterns:
            match = re.search(pattern, normalized_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_dates(self, text: str, current_date: date) -> tuple[date | None, date | None]:
        between_match = re.search(
            r"between (\d{4}-\d{2}-\d{2}) and (\d{4}-\d{2}-\d{2})", text, re.IGNORECASE
        )
        if between_match:
            return date.fromisoformat(between_match.group(1)), date.fromisoformat(between_match.group(2))

        q_match = re.search(r"q([1-4])\s+(\d{4})", text, re.IGNORECASE)
        if q_match:
            quarter = int(q_match.group(1))
            year = int(q_match.group(2))
            start_month = (quarter - 1) * 3 + 1
            end_month = start_month + 2
            end_day = calendar.monthrange(year, end_month)[1]
            return date(year, start_month, 1), date(year, end_month, end_day)

        month_match = re.search(
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b",
            text,
            re.IGNORECASE,
        )
        if month_match:
            month_name = month_match.group(1)
            year = int(month_match.group(2))
            month = list(calendar.month_name).index(month_name.capitalize())
            end_day = calendar.monthrange(year, month)[1]
            return date(year, month, 1), date(year, month, end_day)

        if "last month" in text.lower():
            first_day_of_current_month = current_date.replace(day=1)
            last_day_previous_month = first_day_of_current_month - timedelta(days=1)
            return (
                last_day_previous_month.replace(day=1),
                last_day_previous_month,
            )

        numeric_month_match = re.search(r"\b(0?[1-9]|1[0-2])[/\-](\d{4})\b", text, re.IGNORECASE)
        if numeric_month_match:
            month = int(numeric_month_match.group(1))
            year = int(numeric_month_match.group(2))
            end_day = calendar.monthrange(year, month)[1]
            return date(year, month, 1), date(year, month, end_day)

        return None, None
