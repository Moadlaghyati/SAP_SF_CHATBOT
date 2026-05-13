from __future__ import annotations

import calendar as _cal
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

LOGGER = logging.getLogger(__name__)

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    # French
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

_HOLIDAY_KEYWORDS = re.compile(
    r"\b(holiday|holidays|public holiday|jour férié|jours fériés|férié|ferie|"
    r"bank holiday|national day|fête nationale|jour de congé|congé public|"
    r"eid|ramadan|throne day|labour day|independence|new year|mawlid|"
    r"fête du trône|fête du travail|indépendance|nouvel an|marche verte|"
    r"aïd|aid al|eid al|hijri|islamic)\b",
    re.IGNORECASE,
)

_SCHEDULE_KEYWORDS = re.compile(
    r"\b(work schedule|working hours|work hours|horaire|horaires de travail|"
    r"schedule|working days|jours de travail|heures de travail|work day|"
    r"what time|start time|end time|opening hours|heure de début|heure de fin|"
    r"hours per week|heures par semaine|days per week|jours par semaine)\b",
    re.IGNORECASE,
)


@dataclass
class ScheduleResult:
    handled: bool
    status: str
    intent: str = "unknown"
    holidays: list[dict] = field(default_factory=list)
    work_schedule: dict | None = None
    date_range: dict = field(default_factory=dict)
    message: str = ""
    summary_text: str = ""


def detect_schedule_intent(message: str) -> tuple[bool, str]:
    """Return (should_handle, intent) where intent is 'holiday' or 'work_schedule'."""
    if _HOLIDAY_KEYWORDS.search(message):
        return True, "holiday"
    if _SCHEDULE_KEYWORDS.search(message):
        return True, "work_schedule"
    return False, "unknown"


def _extract_date_range(message: str, current_date: date) -> tuple[str, str]:
    """Extract start/end dates from the message, defaulting to current year."""
    today = current_date
    lowered = message.lower()

    # Specific ISO date
    iso_match = re.search(r"(\d{4}-\d{2}-\d{2})", message)
    if iso_match:
        d = iso_match.group(1)
        return d, d

    # Named month + year
    for month_name, month_num in _MONTH_MAP.items():
        year_match = re.search(rf"\b{re.escape(month_name)}\s+(\d{{4}})\b", lowered)
        if year_match:
            year = int(year_match.group(1))
            last_day = _cal.monthrange(year, month_num)[1]
            return f"{year}-{month_num:02d}-01", f"{year}-{month_num:02d}-{last_day:02d}"

    # "this month"
    if "this month" in lowered or "ce mois" in lowered:
        first = today.replace(day=1)
        last = today.replace(day=_cal.monthrange(today.year, today.month)[1])
        return first.isoformat(), last.isoformat()

    # "next month"
    if "next month" in lowered or "mois prochain" in lowered:
        if today.month == 12:
            first = date(today.year + 1, 1, 1)
        else:
            first = date(today.year, today.month + 1, 1)
        last = first.replace(day=_cal.monthrange(first.year, first.month)[1])
        return first.isoformat(), last.isoformat()

    # "today"
    if "today" in lowered or "aujourd'hui" in lowered:
        return today.isoformat(), today.isoformat()

    # "this week"
    if "this week" in lowered or "cette semaine" in lowered:
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        return monday.isoformat(), sunday.isoformat()

    # Specific year mentioned
    year_match = re.search(r"\b(20\d{2})\b", message)
    if year_match:
        year = int(year_match.group(1))
        return f"{year}-01-01", f"{year}-12-31"

    # Default: current year
    return f"{today.year}-01-01", f"{today.year}-12-31"


def _extract_employee_name(message: str) -> str | None:
    patterns = [
        r"(?:schedule|horaire|hours)\s+(?:for|de|of)\s+([A-Z][a-zA-ZÀ-ÿ]+(?:\s+[A-Z][a-zA-ZÀ-ÿ]+)?)",
        r"([A-Z][a-zA-ZÀ-ÿ]+(?:\s+[A-Z][a-zA-ZÀ-ÿ]+)?)'s?\s+(?:schedule|work|horaire)",
    ]
    for pat in patterns:
        m = re.search(pat, message)
        if m:
            return m.group(1).strip()
    return None


class ScheduleAgent:
    def __init__(self, *, client, current_date_provider=None):
        self._client = client
        self._current_date_provider = current_date_provider or date.today

    async def handle(
        self,
        message: str,
        *,
        acting_sap_user_id: str | None = None,
        step_recorder=None,
        employee_name: str | None = None,
        employee_found: bool = True,
        intent_override: str | None = None,
    ) -> ScheduleResult:
        if intent_override in ("holiday", "work_schedule"):
            should_handle, intent = True, intent_override
        else:
            should_handle, intent = detect_schedule_intent(message)
        if not should_handle:
            return ScheduleResult(handled=False, status="not_applicable")

        today = self._current_date_provider()
        start_date, end_date = _extract_date_range(message, today)

        def _step(name, status, detail, data=None):
            if step_recorder:
                step_recorder(name, status, detail, data)

        if intent == "holiday":
            _step("schedule_agent_holidays", "running", f"Fetching holidays {start_date} → {end_date}")
            try:
                holidays = await self._client.get_holidays(start_date=start_date, end_date=end_date)
            except Exception as exc:
                LOGGER.warning("[ScheduleAgent] get_holidays failed: %s", exc)
                return ScheduleResult(
                    handled=True, status="error",
                    message=f"Could not retrieve holiday data: {exc}",
                )
            # Filter to upcoming-only when user says "upcoming"
            if "upcoming" in message.lower():
                holidays = [h for h in holidays if h.get("date", "") >= today.isoformat()]
            _step("schedule_agent_holidays", "completed", f"Found {len(holidays)} holidays", {"count": len(holidays)})
            summary = _build_holiday_summary(holidays, start_date, end_date, employee_name=employee_name, employee_found=employee_found)
            return ScheduleResult(
                handled=True, status="success", intent="holiday",
                holidays=holidays,
                date_range={"startDate": start_date, "endDate": end_date},
                summary_text=summary,
            )

        # work_schedule intent
        employee_name = _extract_employee_name(message)
        user_id = acting_sap_user_id
        if employee_name and hasattr(self._client, "resolve_user_id_by_name"):
            try:
                resolved = await self._client.resolve_user_id_by_name(employee_name)
                if resolved:
                    user_id = resolved
            except Exception:
                pass

        if not user_id:
            return ScheduleResult(
                handled=True, status="needs_clarification",
                message="Please specify which employee's work schedule you'd like to see.",
            )

        _step("schedule_agent_work_schedule", "running", f"Fetching work schedule for {user_id}")
        try:
            ws = await self._client.get_work_schedule(user_id=user_id)
        except Exception as exc:
            LOGGER.warning("[ScheduleAgent] get_work_schedule failed: %s", exc)
            ws = None

        if not ws:
            return ScheduleResult(
                handled=True, status="not_found",
                message="No work schedule found for this employee.",
            )

        _step("schedule_agent_work_schedule", "completed", "Work schedule retrieved", {"schedule": ws.get("schedule_name")})
        summary = _build_schedule_summary(ws)
        return ScheduleResult(
            handled=True, status="success", intent="work_schedule",
            work_schedule=ws,
            summary_text=summary,
        )


def _build_holiday_summary(holidays: list[dict], start_date: str, end_date: str, employee_name: str | None = None, employee_found: bool = True) -> str:
    if employee_name and not employee_found:
        note = f"Employee **{employee_name}** was not found in the system. "
    elif employee_name and employee_found:
        note = f"Public holidays for **{employee_name}**. "
    else:
        note = ""

    if not holidays:
        return note + f"No public holidays found between {start_date} and {end_date}."

    return note + f"Found **{len(holidays)}** public holiday(s) between {start_date} and {end_date}."


def _build_schedule_summary(ws: dict) -> str:
    name = ws.get("employee_display_name", ws.get("employee_id", "Employee"))
    sched = ws.get("schedule_name", "Standard")
    days = ws.get("days_per_week", 5)
    hours = ws.get("hours_per_week", 40)
    work_days = ws.get("work_days", [])
    lines = [f"**{name}** — {sched}", f"• {days} days/week · {hours} hours/week"]
    if work_days:
        lines.append("• Working days:")
        for d in work_days:
            lines.append(f"  - {d['day']}: {d['start']} – {d['end']} ({d['hours']}h)")
    return "\n".join(lines)
