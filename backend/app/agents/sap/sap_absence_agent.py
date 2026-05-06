from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from app.agents.sap.absence_extraction import extract_absence_retrieval_params
from app.agents.sap.absence_formatter import format_absence_summary, format_workforce_absence_summary
from app.agents.sap.absence_intent import detect_absence_intent
from app.agents.sap.absence_schemas import (
    AbsenceRetrievalParams,
    SapAbsenceClarificationResult,
    SapAbsenceErrorResult,
    SapAbsenceNotApplicableResult,
    SapAbsenceResult,
    SapAbsenceSuccessResult,
)
from app.services.errors import ConnectorUnavailableError


class SapAbsenceAgent:
    def __init__(self, *, client, current_date_provider, llm_client=None):
        self._client = client
        self._current_date_provider = current_date_provider
        self._llm_client = llm_client

    async def _extract_params(self, message: str, current_date: date) -> AbsenceRetrievalParams:
        if self._llm_client is not None:
            result = await self._llm_client.extract_absence_params(message, current_date)

            # Normalise scope — guard against spaces or unexpected values from the LLM
            _valid_scopes = {"self", "specific_employee", "direct_report_or_team", "workforce", "comparison", "unknown"}
            scope = (result.scope or "unknown").lower().replace(" ", "_")
            if scope not in _valid_scopes:
                scope = "unknown"

            # Normalise dates — empty strings count as missing; default to current year
            start_date = result.start_date if result.start_date else None
            end_date = result.end_date if result.end_date else None

            # If the LLM returned today as both start and end without the user
            # explicitly saying "today", treat it as a missing date and fall back
            # to the full current year.
            today_iso = current_date.isoformat()
            user_said_today = any(w in message.lower() for w in ("today", "aujourd'hui", "maintenant", "right now", "currently"))
            if not user_said_today and start_date == today_iso and end_date == today_iso:
                start_date = None
                end_date = None

            if not start_date:
                start_date = date(current_date.year, 1, 1).isoformat()
            if not end_date:
                end_date = date(current_date.year, 12, 31).isoformat()

            def _clean(val: str | None) -> str | None:
                if not val or val.strip().lower() in ("null", "none", ""):
                    return None
                return val

            employee_name = _clean(result.employee_name)
            employee_name_b = _clean(result.employee_name_b)
            user_id = _clean(result.user_id)

            # Never trust the LLM's clarification for dates — we always apply defaults.
            # Only ask for clarification when scope is specific_employee and no employee can be identified.
            needs_clarification = (
                scope == "specific_employee"
                and not employee_name
                and not user_id
            )
            clarification_message = result.clarification_message if needs_clarification else None

            return AbsenceRetrievalParams(
                raw_user_question=message,
                scope=scope,  # type: ignore[arg-type]
                employee_name=employee_name,
                employee_name_b=employee_name_b,
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                missing_required_fields=["employee_identifier"] if needs_clarification else [],
                clarification_message=clarification_message,
            )
        return extract_absence_retrieval_params(message, current_date=current_date)

    async def _resolve_display_name(self, user_id: str, hint: str | None = None) -> str | None:
        if hint:
            return hint
        try:
            names = await self._client.get_display_names_for_user_ids([user_id])
            return names.get(user_id)
        except Exception:
            return None

    async def _resolve_name_to_id(
        self, name: str, local_map: dict[str, str] | None = None
    ) -> str | None:
        """Resolve an employee display name to their SAP userId.
        Checks the local FRMF employee map first to avoid SAP User entity
        mismatches, then falls back to the SAP name-lookup API.
        """
        if local_map:
            local_id = local_map.get(name.strip().lower())
            if local_id:
                return local_id
        return await self._client.resolve_user_id_by_name(name)

    async def handle(
        self,
        message: str,
        step_recorder: Callable[[str, str, str, dict[str, Any] | None], None] | None = None,
        acting_sap_user_id: str | None = None,
        acting_user_display_name: str | None = None,
        allowed_employee_ids: list[str] | None = None,
        local_name_to_id: dict[str, str] | None = None,
        all_sap_user_ids: list[str] | None = None,
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
        params = await self._extract_params(message, current_date)
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

        # ── scope: comparison ─────────────────────────────────────────────────
        if params.scope == "comparison":
            if not params.employee_name or not params.employee_name_b:
                return SapAbsenceClarificationResult(
                    handled=True, type="sap_absences", status="needs_clarification",
                    message="Please name both employees to compare, e.g. \"Compare Walid Regragi and Ilham Tbato absences this year\".",
                    missing_fields=["employee_name", "employee_name_b"],
                )
            assert params.start_date is not None
            assert params.end_date is not None

            # Resolve both employee names to user IDs (local map first, SAP fallback)
            user_id_a: str | None = None
            user_id_b: str | None = None
            for attr, name in [("a", params.employee_name), ("b", params.employee_name_b)]:
                try:
                    uid = await self._resolve_name_to_id(name, local_name_to_id)
                except ConnectorUnavailableError:
                    uid = None
                if not uid:
                    return SapAbsenceClarificationResult(
                        handled=True, type="sap_absences", status="needs_clarification",
                        message=f"Could not find a SAP user ID for \"{name}\". Please check the spelling or provide the userId directly.",
                        missing_fields=["user_id"],
                    )
                if attr == "a":
                    user_id_a = uid
                else:
                    user_id_b = uid

            assert user_id_a and user_id_b
            absences_a: list = []
            absences_b: list = []
            for uid, container in [(user_id_a, absences_a), (user_id_b, absences_b)]:
                try:
                    container.extend(await self._client.get_employee_absences(
                        user_id=uid, start_date=params.start_date, end_date=params.end_date,
                    ))
                except ConnectorUnavailableError:
                    pass

            def _stats(absences: list) -> dict:
                total_days = sum(a.quantity_in_days or 0.0 for a in absences)
                by_type: dict = {}
                for a in absences:
                    t = a.absence_type or "Unknown"
                    if t not in by_type:
                        by_type[t] = {"count": 0, "days": 0.0}
                    by_type[t]["count"] += 1
                    by_type[t]["days"] = round(by_type[t]["days"] + (a.quantity_in_days or 0.0), 2)
                return {"total_absences": len(absences), "total_days": round(total_days, 2), "by_type": by_type}

            comparison = {
                "employee_a": {"user_id": user_id_a, "name": params.employee_name, "stats": _stats(absences_a)},
                "employee_b": {"user_id": user_id_b, "name": params.employee_name_b, "stats": _stats(absences_b)},
            }
            all_absences = list(absences_a) + list(absences_b)
            member_names = {user_id_a: params.employee_name, user_id_b: params.employee_name_b}
            summary = (
                f"Absence comparison for {params.employee_name} vs {params.employee_name_b} "
                f"({params.start_date} to {params.end_date}):\n"
                f"• {params.employee_name}: {len(absences_a)} absence(s), "
                f"{comparison['employee_a']['stats']['total_days']} day(s)\n"
                f"• {params.employee_name_b}: {len(absences_b)} absence(s), "
                f"{comparison['employee_b']['stats']['total_days']} day(s)"
            )
            record("sap_absence_query", "completed", "Comparison query completed.", {"absence_count": len(all_absences)})
            return SapAbsenceSuccessResult(
                handled=True, type="sap_absences", status="success",
                employee=None,
                date_range={"startDate": params.start_date, "endDate": params.end_date},
                absences=all_absences,
                member_names=member_names,
                comparison=comparison,
                summary_text=summary,
            )

        # ── scope: unknown ────────────────────────────────────────────────────
        if params.scope == "unknown":
            record("sap_scope_resolution", "needs_clarification", "Could not determine who the query is about.")
            return SapAbsenceClarificationResult(
                handled=True,
                type="sap_absences",
                status="needs_clarification",
                message=(
                    "I'm not sure who you'd like to check absences for. "
                    "You can ask about:\n"
                    "• Yourself — \"Show my absences this month\"\n"
                    "• A specific employee — \"Show Walid Regragi's absences in May\"\n"
                    "• Your team — \"Who on my team is absent this week?\"\n"
                    "• The whole company — \"Who is absent today?\""
                ),
                missing_fields=["target_scope"],
            )

        # ── scope: self ───────────────────────────────────────────────────────
        if params.scope == "self":
            record("sap_scope_resolution", "running", "Detected self-query scope.", {"acting_sap_user_id": bool(acting_sap_user_id)})
            if not acting_sap_user_id:
                return SapAbsenceClarificationResult(
                    handled=True,
                    type="sap_absences",
                    status="needs_clarification",
                    message=(
                        "To show your own absences I need your SAP SuccessFactors userId. "
                        "Please provide it (e.g. \"Show my absences, my userId is jdoe\") "
                        "or ask your administrator to configure SAP_ACTING_USER_ID."
                    ),
                    missing_fields=["acting_user_id"],
                )
            record("sap_scope_resolution", "completed", "Using acting user as query target.")
            # fall through with acting_sap_user_id as the resolved user
            resolved_user_id = acting_sap_user_id
            assert params.start_date is not None
            assert params.end_date is not None
            try:
                record("sap_absence_query", "running", "Querying acting user's own absences.", {"user_id_present": True})
                absences = await self._client.get_employee_absences(
                    user_id=resolved_user_id,
                    start_date=params.start_date,
                    end_date=params.end_date,
                )
            except ConnectorUnavailableError as exc:
                return SapAbsenceErrorResult(
                    handled=True, type="sap_absences", status="error",
                    message=str(exc), safe_error_code="sap_unavailable",
                )
            record("sap_absence_query", "completed", "Self-query completed.", {"absence_count": len(absences)})
            display_name = await self._resolve_display_name(resolved_user_id, hint=acting_user_display_name)
            return SapAbsenceSuccessResult(
                handled=True, type="sap_absences", status="success",
                employee={"userId": resolved_user_id, **({"name": display_name} if display_name else {})},
                date_range={"startDate": params.start_date, "endDate": params.end_date},
                absences=absences,
                summary_text=format_absence_summary(
                    user_id=resolved_user_id,
                    start_date=params.start_date,
                    end_date=params.end_date,
                    absences=absences,
                    employee_name=display_name,
                ),
            )

        # ── scope: direct_report_or_team ──────────────────────────────────────
        if params.scope == "direct_report_or_team":
            record("sap_scope_resolution", "running", "Detected team/direct-reports scope.", {"acting_sap_user_id": bool(acting_sap_user_id)})
            if not acting_sap_user_id:
                return SapAbsenceClarificationResult(
                    handled=True,
                    type="sap_absences",
                    status="needs_clarification",
                    message=(
                        "To show your team's absences I need your SAP SuccessFactors userId. "
                        "Please ask your administrator to configure SAP_ACTING_USER_ID, "
                        "or specify the employee name instead."
                    ),
                    missing_fields=["acting_user_id"],
                )
            assert params.start_date is not None
            assert params.end_date is not None

            # Use the pre-authorised employee list (FRMF members) when available —
            # it is more reliable than EmpJob.managerId which only covers 1-level reports
            # and uses alphanumeric SAP userIds that may differ from our numeric IDs.
            if allowed_employee_ids and len(allowed_employee_ids) > 1:
                team_ids = [uid for uid in allowed_employee_ids if uid != acting_sap_user_id]
                record(
                    "sap_scope_resolution",
                    "completed",
                    "Using authorised employee list as team scope.",
                    {"team_member_count": len(team_ids)},
                )
            else:
                record("sap_scope_resolution", "running", "Fetching direct reports via org hierarchy (managerId).")
                team_ids = await self._client.get_direct_report_user_ids(
                    manager_user_id=acting_sap_user_id,
                    manager_display_name=acting_user_display_name,
                )
                record(
                    "sap_scope_resolution",
                    "completed",
                    "Resolved direct reports from org hierarchy.",
                    {"direct_report_count": len(team_ids)},
                )

            if not team_ids:
                return SapAbsenceClarificationResult(
                    handled=True,
                    type="sap_absences",
                    status="needs_clarification",
                    message=(
                        f"No team members were found for user '{acting_sap_user_id}'. "
                        "Please verify that SAP_ACTING_USER_ID is correct and that you have "
                        "direct reports configured in SAP SuccessFactors."
                    ),
                    missing_fields=["direct_reports"],
                )
            all_absences: list = []
            for uid in team_ids:
                try:
                    all_absences.extend(await self._client.get_employee_absences(
                        user_id=uid, start_date=params.start_date, end_date=params.end_date,
                    ))
                except ConnectorUnavailableError:
                    pass
            absent_user_ids = list({a.user_id for a in all_absences if a.user_id})
            try:
                member_names = await self._client.get_display_names_for_user_ids(absent_user_ids)
            except Exception:
                member_names = {}
            if local_name_to_id:
                local_id_to_name = {v: k.title() for k, v in local_name_to_id.items()}
                for uid in absent_user_ids:
                    if uid not in member_names and uid in local_id_to_name:
                        member_names[uid] = local_id_to_name[uid]
            record("sap_absence_query", "completed", "Direct-reports absence query completed.", {"absence_count": len(all_absences)})
            return SapAbsenceSuccessResult(
                handled=True, type="sap_absences", status="success",
                employee=None,
                date_range={"startDate": params.start_date, "endDate": params.end_date},
                absences=all_absences,
                member_names=member_names,
                summary_text=format_workforce_absence_summary(
                    start_date=params.start_date, end_date=params.end_date, absences=all_absences,
                ),
            )

        if params.scope == "workforce":
            assert params.start_date is not None
            assert params.end_date is not None

            if allowed_employee_ids:
                record(
                    "sap_absence_query",
                    "running",
                    "Querying SuccessFactors EmployeeTime for each authorised employee.",
                    {"scope": "workforce", "employee_count": len(allowed_employee_ids)},
                )
                all_absences: list = []
                for uid in allowed_employee_ids:
                    try:
                        all_absences.extend(await self._client.get_employee_absences(
                            user_id=uid,
                            start_date=params.start_date,
                            end_date=params.end_date,
                        ))
                    except ConnectorUnavailableError:
                        pass
                absent_user_ids = list({a.user_id for a in all_absences if a.user_id})
                try:
                    member_names = await self._client.get_display_names_for_user_ids(absent_user_ids)
                except Exception:
                    member_names = {}
                if local_name_to_id:
                    local_id_to_name = {v: k.title() for k, v in local_name_to_id.items()}
                    for uid in absent_user_ids:
                        if uid not in member_names and uid in local_id_to_name:
                            member_names[uid] = local_id_to_name[uid]
                record("sap_absence_query", "completed", "Per-employee workforce query completed.", {"absence_count": len(all_absences)})
                return SapAbsenceSuccessResult(
                    handled=True,
                    type="sap_absences",
                    status="success",
                    employee=None,
                    date_range={"startDate": params.start_date, "endDate": params.end_date},
                    absences=all_absences,
                    member_names=member_names,
                    summary_text=format_workforce_absence_summary(
                        start_date=params.start_date,
                        end_date=params.end_date,
                        absences=all_absences,
                    ),
                )

            # No allow-list — fall back to full-org SAP query
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
                record("sap_absence_query", "error", "SAP workforce absence query failed.", {"safe_error_code": "sap_unavailable"})
                return SapAbsenceErrorResult(
                    handled=True,
                    type="sap_absences",
                    status="error",
                    message=str(exc),
                    safe_error_code="sap_unavailable",
                )

            record("sap_absence_query", "completed", "SuccessFactors EmployeeTime workforce query completed.", {"absence_count": len(absences)})
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
                user_id = await self._resolve_name_to_id(params.employee_name, local_name_to_id)
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
        display_name = await self._resolve_display_name(user_id, hint=params.employee_name)
        return SapAbsenceSuccessResult(
            handled=True,
            type="sap_absences",
            status="success",
            employee={"userId": user_id, **({"name": display_name} if display_name else {})},
            date_range={"startDate": params.start_date, "endDate": params.end_date},
            absences=absences,
            summary_text=format_absence_summary(
                user_id=user_id,
                start_date=params.start_date,
                end_date=params.end_date,
                absences=absences,
                employee_name=display_name,
            ),
        )
