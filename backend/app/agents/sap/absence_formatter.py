from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.agents.sap.absence_schemas import EmployeeAbsence


def normalize_employee_absences(payload: Any) -> list[EmployeeAbsence]:
    results = _extract_results(payload)
    normalized: list[EmployeeAbsence] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        normalized.append(
            EmployeeAbsence(
                user_id=str(item.get("userId") or ""),
                start_date=_normalize_sap_date(item.get("startDate")),
                end_date=_normalize_sap_date(item.get("endDate")),
                absence_type=_string_or_none(item.get("timeType") or item.get("absenceType")),
                approval_status=_string_or_none(item.get("approvalStatus")),
                quantity_in_days=_number_or_none(item.get("quantityInDays")),
                quantity_in_hours=_number_or_none(item.get("quantityInHours")),
                external_code=_string_or_none(item.get("externalCode")),
                raw=item,
            )
        )
    return normalized


def format_absence_summary(
    *,
    user_id: str,
    start_date: str,
    end_date: str,
    absences: list[EmployeeAbsence],
) -> str:
    if not absences:
        return f"No absence records were found for user {user_id} from {start_date} to {end_date}."

    lines = [
        f"Found **{len(absences)} absence record{'s' if len(absences) != 1 else ''}** for user **{user_id}** from {start_date} to {end_date}.",
        "",
        "| Absence type | Start date | End date | Approval status | Days | Hours |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ]
    for absence in absences:
        lines.append(
            "| {absence_type} | {start_date} | {end_date} | {status} | {days} | {hours} |".format(
                absence_type=_markdown_cell(absence.absence_type or "Absence"),
                start_date=_markdown_cell(absence.start_date or "n/a"),
                end_date=_markdown_cell(absence.end_date or "n/a"),
                status=_markdown_cell(absence.approval_status or "Status unavailable"),
                days=_format_optional_number(absence.quantity_in_days),
                hours=_format_optional_number(absence.quantity_in_hours),
            )
        )
    return "\n".join(lines)


def format_workforce_absence_summary(
    *,
    start_date: str,
    end_date: str,
    absences: list[EmployeeAbsence],
) -> str:
    period = start_date if start_date == end_date else f"{start_date} to {end_date}"
    if not absences:
        return f"No absence records were found for employees on {period}."

    lines = [
        f"Found **{len(absences)} employee absence record{'s' if len(absences) != 1 else ''}** on {period}.",
        "",
        "| User | Absence type | Start date | End date | Approval status | Days | Hours |",
        "| --- | --- | --- | --- | --- | ---: | ---: |",
    ]
    for absence in absences:
        lines.append(
            "| {user_id} | {absence_type} | {start_date} | {end_date} | {status} | {days} | {hours} |".format(
                user_id=_markdown_cell(absence.user_id or "Unknown user"),
                absence_type=_markdown_cell(absence.absence_type or "Absence"),
                start_date=_markdown_cell(absence.start_date or "n/a"),
                end_date=_markdown_cell(absence.end_date or "n/a"),
                status=_markdown_cell(absence.approval_status or "Status unavailable"),
                days=_format_optional_number(absence.quantity_in_days),
                hours=_format_optional_number(absence.quantity_in_hours),
            )
        )
    return "\n".join(lines)


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value.is_integer():
        return str(int(value))
    return f"{value:g}"


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _extract_results(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        data = payload.get("d")
        if isinstance(data, dict) and isinstance(data.get("results"), list):
            return data["results"]
        if isinstance(payload.get("results"), list):
            return payload["results"]
    if isinstance(payload, list):
        return payload
    return []


def _normalize_sap_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        if value.startswith("/Date("):
            match = re.search(r"/Date\((-?\d+)(?:[+-]\d+)?\)/", value)
            if not match:
                return value
            milliseconds = int(match.group(1))
            return datetime.fromtimestamp(milliseconds / 1000, tz=UTC).date().isoformat()
        return value[:10] if len(value) >= 10 else value
    return str(value)


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
