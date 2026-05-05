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


def _safe_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _find_invalid_iso_dates(text: str) -> list[str]:
    return [m for m in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text) if _safe_date(m) is None]


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

    employee_name: str | None = None
    employee_name_b: str | None = None

    if scope == "comparison":
        employee_name, employee_name_b = _extract_two_employee_names(text)
    else:
        employee_name = None if user_id else _extract_employee_name(text)

    # Refine the coarse "employee" scope into specific_employee or unknown
    if scope == "employee":
        scope = "specific_employee" if (user_id or employee_name) else "unknown"

    if start_date is None or end_date is None:
        invalid_dates = _find_invalid_iso_dates(text)
        if invalid_dates:
            bad = invalid_dates[0]
            return AbsenceRetrievalParams(
                scope=scope,
                employee_name=employee_name,
                user_id=user_id,
                start_date=None,
                end_date=None,
                year=None,
                month=None,
                raw_user_question=message,
                missing_required_fields=["valid_date_range"],
                clarification_message=(
                    f"The date \"{bad}\" is not valid "
                    f"(e.g. June only has 30 days, not 31). "
                    f"Please correct the date and try again."
                ),
            )
        year = current_date.year
        start_date = date(year, 1, 1).isoformat()
        end_date = date(year, 12, 31).isoformat()

    missing_required_fields: list[str] = []
    if scope == "specific_employee" and not user_id and not employee_name:
        missing_required_fields.append("employee_identifier")

    return AbsenceRetrievalParams(
        scope=scope,
        employee_name=employee_name,
        employee_name_b=employee_name_b,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        year=year,
        month=month,
        raw_user_question=message,
        missing_required_fields=missing_required_fields,
    )


def _detect_scope(lowered: str) -> str:
    # 0. Comparison — "compare NAME1 and NAME2", "NAME1 vs NAME2"
    comparison_patterns = [
        r"\bcompare\b",
        r"\bcomparison\b",
        r"\bvs\.?\b",
        r"\bversus\b",
        r"\babsence\s+patterns?\b",
    ]
    if any(re.search(p, lowered) for p in comparison_patterns):
        # If this is a temporal comparison for ONE person (e.g., "compare Walid this year and last year"),
        # don't treat it as a two-employee comparison — fall through to employee scope.
        _two_periods = re.search(
            r"\b(?:this year|last year|next year|\d{4})\b.+\band\b.+\b(?:this year|last year|next year|\d{4})\b",
            lowered,
        )
        if not _two_periods:
            return "comparison"

    # 1. Self — "my absences", "do I have", "my leaves", etc.
    # But "show my absences for [name]" means specific_employee, not self.
    _FOR_PERSON = re.compile(
        r"\bfor\s+(?!(?:my|our|this|last|next|the|a|an|your|their)\b)"
        r"[A-Za-z][A-Za-z']+(?:\s+[A-Za-z][A-Za-z']+)?\b"
    )
    self_patterns = [
        r"\bmy\s+(?:absences?|leaves?|pto|vacation|time\s+off|sick\s+leave|days?\s+off)\b",
        r"\b(?:do|did|will|have)\s+i\s+(?:have|had|take|taken)\b",
        r"\bhow\s+many\s+(?:absences?|leaves?|days?)\s+(?:do|did|will|have)\s+i\b",
        r"\bshow\s+me\s+my\s+(?:absences?|leaves?|pto|vacation)\b",
        r"\bmy\s+(?:remaining|current|upcoming|past)\s+(?:absences?|leaves?|pto|vacation|days?\s+off)\b",
        r"\bi\s+(?:have|had|will\s+have|am\s+taking|took)\b.*\b(?:absence|leave|vacation|day\s+off|pto)\b",
        r"\bmy\s+absence\s+(?:history|record|summary|balance)\b",
    ]
    if any(re.search(p, lowered, re.IGNORECASE) for p in self_patterns):
        # Override: if a person's name follows "for", it's a specific-employee query
        if _FOR_PERSON.search(lowered):
            return "employee"
        return "self"

    # 2. Direct report / team — "my team", "my direct reports", "my department's absences"
    team_patterns = [
        r"\bmy\s+(?:team|direct\s+reports?|department|group|staff|subordinates?)\b.*\b(?:absences?|leaves?|pto|vacation|absent|off)\b",
        r"\b(?:absences?|leaves?|pto|vacation|absent|off)\b.*\bmy\s+(?:team|direct\s+reports?|department|group|staff)\b",
        r"\bmy\s+(?:team|direct\s+reports?)\s+(?:absences?|leaves?|members?\s+absent)\b",
        r"\bwho\s+(?:in|from|on)\s+my\s+(?:team|department|group)\s+(?:is|are|will\s+be|was|were)\s+(?:absent|on\s+leave|off)\b",
    ]
    if any(re.search(p, lowered, re.IGNORECASE) for p in team_patterns):
        return "direct_report_or_team"

    # 3. Workforce / company-wide
    # \bemploy(?:ee?)?s?\b matches: employee, employees, employe, employes, employ, employs
    _EMP = r"\bemploy(?:ee?)?s?\b"
    workforce_patterns = [
        r"\bwho\s+(?:is|will\s+(?:be\s+)?|was|were|are|(?:is\s+)?going\s+to\s+(?:be\s+)?)\s*(?:absent|on\s+leave|on\s+vacation|off)\b",
        r"\bwho\s+will\s+absent\b",
        r"\bcan\s+(?:you\s+)?(?:see|show|tell\s+me)\s+who\s+(?:will\s+)?(?:be\s+)?absent\b",
        r"\bwho\s+(?:will\s+)?(?:be\s+)?absent\b",
        _EMP + r".*\b(?:absent|on\s+leave|on\s+vacation|vacations?|off)\b",
        r"\bwhich\s+" + _EMP + r".*\b(?:absent|on\s+leave|on\s+vacation|vacations?|off)\b",
        r"\bany\s+" + _EMP + r".*\b(?:absent|on\s+leave|on\s+vacation|vacations?|off)\b",
        _EMP + r"\s+that\s+(?:will\s+)?(?:have|take|be\s+on)\s+(?:vacations?|leave|time\s+off|pto)\b",
        _EMP + r"\s+(?:who|that)\s+(?:will\s+)?(?:be\s+(?:on\s+)?|have|take)\s+(?:vacations?|leave|time\s+off|pto|absent)\b",
        r"\bwhat\s+(?:are\s+)?(?:the\s+)?" + _EMP + r".*\b(?:vacations?|leave|absent|off|pto)\b",
        r"\blist\s+(?:of\s+)?(?:all\s+)?" + _EMP + r".*\b(?:vacations?|leave|absent|off|pto)\b",
        r"\ball\s+(?:the\s+)?(?:absences?|leaves?|time\s+off|pto|vacations?)\b",
        r"\b(?:company|organization|organisation|workforce|everyone|all\s+" + _EMP + r")\b.*\b(?:absences?|leaves?|time\s+off|pto|vacations?|absent)\b",
        r"\b(?:absences?|leaves?|time\s+off|pto|vacations?)\b.*\b(?:company|organization|organisation|workforce|everyone|all\s+" + _EMP + r")\b",
    ]
    if any(re.search(p, lowered, re.IGNORECASE) for p in workforce_patterns):
        return "workforce"

    # 4 & 5 — specific_employee vs unknown are resolved after name extraction in the caller
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
        start = _safe_date(between_match.group(1))
        end = _safe_date(between_match.group(2))
        if start and end:
            return start.isoformat(), end.isoformat(), start.year, start.month if start.year == end.year else None
        return None, None, None, None

    from_to_match = re.search(
        r"\bfrom\s+(\d{4}-\d{2}-\d{2})\s+(?:to|until|through)\s+(\d{4}-\d{2}-\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if from_to_match:
        start = _safe_date(from_to_match.group(1))
        end = _safe_date(from_to_match.group(2))
        if start and end:
            return start.isoformat(), end.isoformat(), start.year, start.month if start.year == end.year else None
        return None, None, None, None

    iso_dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if len(iso_dates) == 1:
        single_day = _safe_date(iso_dates[0])
        if single_day:
            return single_day.isoformat(), single_day.isoformat(), single_day.year, single_day.month
        return None, None, None, None
    if len(iso_dates) >= 2:
        start = _safe_date(iso_dates[0])
        end = _safe_date(iso_dates[1])
        if start and end:
            return start.isoformat(), end.isoformat(), start.year, start.month if start.year == end.year else None
        return None, None, None, None

    # Combined periods: "this month and next week", "next week and this month" → union
    _has_this_month = "this month" in lowered or "this mounth" in lowered
    _has_next_week = "next week" in lowered
    _has_this_week = "this week" in lowered
    _has_next_month = "next month" in lowered
    if _has_this_month and _has_next_week:
        m_start, m_end, _, _ = _month_range(current_date.year, current_date.month)
        _days = current_date.weekday()
        nw_start = current_date - timedelta(days=_days) + timedelta(days=7)
        nw_end = nw_start + timedelta(days=6)
        start = min(date.fromisoformat(m_start), nw_start)
        end = max(date.fromisoformat(m_end), nw_end)
        return start.isoformat(), end.isoformat(), start.year, None
    if _has_this_month and _has_this_week:
        m_start, m_end, _, _ = _month_range(current_date.year, current_date.month)
        _days = current_date.weekday()
        tw_start = current_date - timedelta(days=_days)
        tw_end = tw_start + timedelta(days=6)
        start = min(date.fromisoformat(m_start), tw_start)
        end = max(date.fromisoformat(m_end), tw_end)
        return start.isoformat(), end.isoformat(), start.year, None
    if _has_next_month and _has_next_week:
        nm_start, nm_end, _, _ = (
            _month_range(current_date.year + 1, 1) if current_date.month == 12
            else _month_range(current_date.year, current_date.month + 1)
        )
        _days = current_date.weekday()
        nw_start = current_date - timedelta(days=_days) + timedelta(days=7)
        nw_end = nw_start + timedelta(days=6)
        start = min(date.fromisoformat(nm_start), nw_start)
        end = max(date.fromisoformat(nm_end), nw_end)
        return start.isoformat(), end.isoformat(), start.year, None

    if "next year" in lowered:
        return _year_range(current_date.year + 1)

    if "this year" in lowered:
        return _year_range(current_date.year)

    if "last year" in lowered:
        return _year_range(current_date.year - 1)

    if "next month" in lowered:
        if current_date.month == 12:
            return _month_range(current_date.year + 1, 1)
        return _month_range(current_date.year, current_date.month + 1)

    _N_WEEKS_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6}
    n_weeks_match = re.search(r"\bnext\s+(one|two|three|four|five|six|\d+)\s+weeks?\b", lowered)
    if n_weeks_match:
        n_weeks = _N_WEEKS_WORDS.get(n_weeks_match.group(1).lower(), 2)
        # Try to find an explicit start date in DD-MM-YYYY or YYYY-MM-DD
        dmy = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
        if dmy:
            try:
                start = date(int(dmy.group(3)), int(dmy.group(2)), int(dmy.group(1)))  # DD-MM-YYYY
            except ValueError:
                try:
                    start = date(int(dmy.group(3)), int(dmy.group(1)), int(dmy.group(2)))  # MM-DD-YYYY
                except ValueError:
                    start = current_date
        else:
            start = current_date
        end = start + timedelta(weeks=n_weeks) - timedelta(days=1)
        return start.isoformat(), end.isoformat(), start.year, None

    if "next week" in lowered:
        days_since_monday = current_date.weekday()
        next_monday = current_date - timedelta(days=days_since_monday) + timedelta(days=7)
        next_sunday = next_monday + timedelta(days=6)
        return next_monday.isoformat(), next_sunday.isoformat(), next_monday.year, None

    if "last week" in lowered:
        days_since_monday = current_date.weekday()
        last_monday = current_date - timedelta(days=days_since_monday) - timedelta(days=7)
        last_sunday = last_monday + timedelta(days=6)
        return last_monday.isoformat(), last_sunday.isoformat(), last_monday.year, None

    if "this week" in lowered:
        days_since_monday = current_date.weekday()
        monday = current_date - timedelta(days=days_since_monday)
        sunday = monday + timedelta(days=6)
        return monday.isoformat(), sunday.isoformat(), monday.year, None

    if "today" in lowered:
        return current_date.isoformat(), current_date.isoformat(), current_date.year, current_date.month

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

    # Two different years connected by "and" — e.g., "this year 2026 and last year 2025"
    two_year_match = re.search(r"\b(20\d{2}|19\d{2})\b.+\band\b.+\b(20\d{2}|19\d{2})\b", text)
    if two_year_match:
        y1, y2 = int(two_year_match.group(1)), int(two_year_match.group(2))
        if y1 != y2:
            start_year, end_year = min(y1, y2), max(y1, y2)
            return date(start_year, 1, 1).isoformat(), date(end_year, 12, 31).isoformat(), end_year, None

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
        # "for NAME between/from/in/this year/next month/..."
        r"\bfor\s+([A-Za-z][A-Za-z' -]+?)\s+(?:between|from|in|this year|last year|last month|this month|next month|next year|$)",
        # "did/do NAME have/had"
        r"\b(?:do|did)\s+([A-Za-z][A-Za-z' -]+?)\s+(?:have|had)\b",
        # "absences for NAME ..."
        r"\b(?:absences?|leaves?|pto|vacation|time off|sick leave)\s+for\s+([A-Za-z][A-Za-z' -]+?)\s*(?:between|from|in|this year|last year|last month|this month|next month|next year|$)",
        # "NAME absences/leaves/..."
        r"\b([A-Za-z][A-Za-z' -]+\s+[A-Za-z][A-Za-z' -]+)\s+(?:absences?|leaves?|pto|vacation|time off)",
        # "absences NAME will have / had"  — "How many absences Walid Regragi will have this month"
        r"\b(?:absences?|leaves?|pto|vacation|time off|sick leave)\s+([A-Za-z][A-Za-z' -]+?)\s+(?:will\s+have\b|will\s+be\b|had\b)",
        # "absences will NAME have"  — "How many absences will Walid Regragi have this month"
        r"\b(?:absences?|leaves?|pto|vacation|time off|sick leave)\s+will\s+([A-Za-z][A-Za-z' -]+?)\s+(?:have\b|had\b)",
        # "NAME will have [N] absences/leaves"
        r"\b([A-Za-z][A-Za-z' -]+?)\s+will\s+have\s+(?:\d+\s+)?(?:absences?|leaves?|pto|vacation|time off|sick leave)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = _clean_name(match.group(1))
            if candidate:
                return candidate
    return None


def _extract_two_employee_names(text: str) -> tuple[str | None, str | None]:
    """Extract two employee names from a comparison query."""
    # "compare NAME1 and/vs NAME2 [absences/...]"
    patterns = [
        r"\bcompare\s+(?:absences?\s+(?:of|for)\s+)?([A-Za-z][A-Za-z' -]+?)\s+(?:and|vs\.?|versus)\s+([A-Za-z][A-Za-z' -]+?)(?:\s+(?:absences?|leaves?|in|for|this|last|next|over|\d{4})|$)",
        r"\bcompar(?:e|ison)\s+(?:between\s+)?([A-Za-z][A-Za-z' -]+?)\s+(?:and|vs\.?|versus)\s+([A-Za-z][A-Za-z' -]+?)(?:\s+(?:absences?|leaves?|in|for|this|last|next|over|\d{4})|$)",
        r"([A-Za-z][A-Za-z' -]+?)\s+(?:vs\.?|versus)\s+([A-Za-z][A-Za-z' -]+?)(?:\s+(?:absences?|leaves?|in|for|this|last|next|over|\d{4})|$)",
        r"\babsence\s+patterns?\s+(?:of|for)\s+([A-Za-z][A-Za-z' -]+?)\s+(?:and|vs\.?|versus)\s+([A-Za-z][A-Za-z' -]+?)(?:\s+(?:in|for|this|last|next|over|\d{4})|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name_a = _clean_name(match.group(1))
            name_b = _clean_name(match.group(2))
            if name_a and name_b:
                return name_a, name_b
    return None, None


_NAME_STOPWORDS = frozenset({
    "list", "show", "get", "find", "fetch", "display", "tell",
    "give", "check", "search", "view", "see", "how", "many",
    "what", "which", "who", "when", "where", "all", "me",
    "will", "take", "have", "are", "were", "was", "be", "been",
    "that", "this", "the", "an", "a", "is", "do", "did",
    "compare", "comparison", "between", "versus", "vs",
})


def _clean_name(value: str) -> str | None:
    cleaned = re.sub(r"\b(user|employee)\b", "", value, flags=re.IGNORECASE).strip(" '\"?.")
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Strip leading command/query words that leaked from the sentence structure
    words = cleaned.split()
    while words and words[0].lower() in _NAME_STOPWORDS:
        words = words[1:]
    cleaned = " ".join(words)
    if len(cleaned) < 2 or re.search(r"\d", cleaned):
        return None
    return cleaned.title()
