from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from app.agents.sap.absence_schemas import AbsenceRetrievalParams


MONTH_LOOKUP = {name.lower(): index for index, name in enumerate(calendar.month_name) if name}
MONTH_LOOKUP.update({name.lower(): index for index, name in enumerate(calendar.month_abbr) if name})
MONTH_LOOKUP.update(
    {
        "janvier": 1,
        "fevrier": 2,
        "février": 2,
        "mars": 3,
        "avril": 4,
        "mai": 5,
        "juin": 6,
        "juillet": 7,
        "aout": 8,
        "août": 8,
        "septembre": 9,
        "octobre": 10,
        "novembre": 11,
        "decembre": 12,
        "décembre": 12,
    }
)


def extract_absence_retrieval_params(
    message: str,
    *,
    current_date: date,
) -> AbsenceRetrievalParams:
    text = message.strip()
    lowered = text.lower()

    scope = _detect_scope(lowered)
    user_id = _extract_user_id(text)
    start_date, end_date, year, month = _extract_date_range(text, current_date=current_date)
    employee_name = None if user_id else _extract_employee_name(text)

    if start_date is None or end_date is None:
        year = current_date.year
        start_date = date(year, 1, 1).isoformat()
        end_date = date(year, 12, 31).isoformat()

    missing_required_fields: list[str] = []
    if scope == "employee" and not user_id and not employee_name:
        missing_required_fields.append("employee_identifier")

    return AbsenceRetrievalParams(
        scope=scope,
        employee_name=employee_name,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        year=year,
        month=month,
        raw_user_question=message,
        missing_required_fields=missing_required_fields,
    )


def _detect_scope(lowered: str) -> str:
    workforce_patterns = [
        r"\bwho\s+(?:is|will be|was|were|are)\s+(?:absent|on\s+leave|on\s+vacation|off)\b",
        r"\bwhich\s+employees?\b.*\b(?:absent|on\s+leave|on\s+vacation|vacations?|off)\b",
        r"\bany\s+employees?\b.*\b(?:absent|on\s+leave|on\s+vacation|vacations?|off)\b",
        r"\bemployees?\s+that\s+(?:will\s+)?(?:have|be\s+on)\s+(?:vacations?|leave|time\s+off)\b",
        r"\ball\s+(?:the\s+)?(?:absences?|leaves?|time\s+off|pto|vacations?)\b",
        r"\b(?:company|organization|organisation|workforce|everyone|all\s+employees?)\b.*\b(?:absences?|leaves?|time\s+off|pto|vacations?|absent)\b",
        r"\b(?:absences?|leaves?|time\s+off|pto|vacations?)\b.*\b(?:company|organization|organisation|workforce|everyone|all\s+employees?)\b",
    ]
    if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in workforce_patterns):
        return "workforce"
    return "employee"


def format_odata_datetime_start(iso_date: str) -> str:
    return f"datetime'{iso_date}T00:00:00'"


def format_odata_datetime_end(iso_date: str) -> str:
    return f"datetime'{iso_date}T23:59:59'"


def _extract_user_id(text: str) -> str | None:
    patterns = [
        r"\buser\s*id\s*(?:is|=|:)?\s*['\"]?([A-Za-z0-9_.-]+)['\"]?",
        r"\buserId\s*(?:is|=|:)?\s*['\"]?([A-Za-z0-9_.-]+)['\"]?",
        r"\bfor\s+user\s+['\"]?([A-Za-z0-9_.-]+)['\"]?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_date_range(text: str, *, current_date: date) -> tuple[str | None, str | None, int | None, int | None]:
    lowered = text.lower()

    between_match = re.search(
        r"\bbetween\s+(\d{4}-\d{2}-\d{2})\s+(?:and|to)\s+(\d{4}-\d{2}-\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if between_match:
        start = date.fromisoformat(between_match.group(1))
        end = date.fromisoformat(between_match.group(2))
        return start.isoformat(), end.isoformat(), start.year, start.month if start.year == end.year else None

    from_to_match = re.search(
        r"\bfrom\s+(\d{4}-\d{2}-\d{2})\s+(?:to|until|through)\s+(\d{4}-\d{2}-\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if from_to_match:
        start = date.fromisoformat(from_to_match.group(1))
        end = date.fromisoformat(from_to_match.group(2))
        return start.isoformat(), end.isoformat(), start.year, start.month if start.year == end.year else None

    iso_dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if len(iso_dates) == 1:
        single_day = date.fromisoformat(iso_dates[0])
        return single_day.isoformat(), single_day.isoformat(), single_day.year, single_day.month
    if len(iso_dates) >= 2:
        start = date.fromisoformat(iso_dates[0])
        end = date.fromisoformat(iso_dates[1])
        return start.isoformat(), end.isoformat(), start.year, start.month if start.year == end.year else None

    if "this year" in lowered:
        return _year_range(current_date.year)

    if "last year" in lowered:
        return _year_range(current_date.year - 1)

    if "last month" in lowered:
        first_day_current_month = current_date.replace(day=1)
        last_day_previous_month = first_day_current_month - timedelta(days=1)
        start = last_day_previous_month.replace(day=1)
        return start.isoformat(), last_day_previous_month.isoformat(), start.year, start.month

    if "this month" in lowered or "this mounth" in lowered:
        return _month_range(current_date.year, current_date.month)

    numeric_month_match = re.search(r"\b(0?[1-9]|1[0-2])[/\-](\d{4})\b", text, re.IGNORECASE)
    if numeric_month_match:
        month = int(numeric_month_match.group(1))
        year = int(numeric_month_match.group(2))
        return _month_range(year, month)

    month_match = re.search(
        r"\b("
        + "|".join(re.escape(name) for name in sorted(MONTH_LOOKUP, key=len, reverse=True))
        + r")\s+(\d{4})\b",
        lowered,
        re.IGNORECASE,
    )
    if month_match:
        month = MONTH_LOOKUP[month_match.group(1).lower()]
        year = int(month_match.group(2))
        return _month_range(year, month)

    year_match = re.search(r"\b(20\d{2}|19\d{2})\b", text)
    if year_match:
        return _year_range(int(year_match.group(1)))

    return None, None, None, None


def _year_range(year: int) -> tuple[str, str, int, None]:
    return date(year, 1, 1).isoformat(), date(year, 12, 31).isoformat(), year, None


def _month_range(year: int, month: int) -> tuple[str, str, int, int]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1).isoformat(), date(year, month, last_day).isoformat(), year, month


def _extract_employee_name(text: str) -> str | None:
    patterns = [
        r"\bfor\s+([A-Z][A-Za-z' -]+?)\s+(?:between|from|in|this year|last year|last month|$)",
        r"\b(?:do|did)\s+([A-Z][A-Za-z' -]+?)\s+(?:have|had)\b",
        r"\b(?:absences?|leaves?|pto|vacation|time off|sick leave)\s+for\s+([A-Z][A-Za-z' -]+?)\s*(?:between|from|in|this year|last year|last month|$)",
        r"\b([A-Z][A-Za-z' -]+\s+[A-Z][A-Za-z' -]+)\s+(?:absences?|leaves?|pto|vacation|time off)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = _clean_name(match.group(1))
            if candidate:
                return candidate
    return None


def _clean_name(value: str) -> str | None:
    cleaned = re.sub(r"\b(user|employee)\b", "", value, flags=re.IGNORECASE).strip(" '\"?.")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned or re.search(r"\d", cleaned):
        return None
    return cleaned
