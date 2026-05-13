from __future__ import annotations

from datetime import date

from app.agents.sap.absence_schemas import EmployeeAbsence
from app.connectors.mock_data import MOCK_ABSENCES, MOCK_EMPLOYEES, MOCK_HOLIDAYS, _build_work_schedules


class MockSapClient:
    """Drop-in replacement for SapSuccessFactorsClient that reads from mock data."""

    def _to_employee_absence(self, record) -> EmployeeAbsence:
        return EmployeeAbsence(
            user_id=record.employee_id,
            start_date=record.start_date.isoformat(),
            end_date=record.end_date.isoformat(),
            absence_type=record.absence_type,
            approval_status="APPROVED",
            quantity_in_days=record.days,
        )

    async def get_employee_absences(self, *, user_id: str, start_date: str, end_date: str) -> list[EmployeeAbsence]:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        return [
            self._to_employee_absence(r)
            for r in MOCK_ABSENCES
            if r.employee_id == user_id and r.start_date >= start and r.end_date <= end
        ]

    async def get_absences(self, *, start_date: str, end_date: str) -> list[EmployeeAbsence]:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        return [
            self._to_employee_absence(r)
            for r in MOCK_ABSENCES
            if r.start_date >= start and r.end_date <= end
        ]

    async def resolve_user_id_by_name(self, employee_name: str) -> str | None:
        lowered = employee_name.strip().lower()
        for emp in MOCK_EMPLOYEES:
            if emp.display_name.lower() == lowered:
                return emp.employee_id
        return None

    async def get_display_names_for_user_ids(self, user_ids: list[str]) -> dict[str, str]:
        id_to_name = {e.employee_id: e.display_name for e in MOCK_EMPLOYEES}
        return {uid: id_to_name[uid] for uid in user_ids if uid in id_to_name}

    async def get_direct_report_user_ids(
        self, *, manager_user_id: str, manager_display_name: str | None = None
    ) -> list[str]:
        return [e.employee_id for e in MOCK_EMPLOYEES if e.manager_employee_id == manager_user_id]

    async def get_employee_department(self, *, user_id: str) -> str | None:
        return None

    async def get_department_employees(self, *, department: str) -> list[str]:
        return []

    async def get_holidays(self, *, start_date: str, end_date: str) -> list[dict]:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        return [
            {"date": h.date, "name": h.name, "name_fr": h.name_fr, "type": h.type}
            for h in MOCK_HOLIDAYS
            if start <= date.fromisoformat(h.date) <= end
        ]

    async def get_work_schedule(self, *, user_id: str) -> dict | None:
        schedules = _build_work_schedules()
        ws = schedules.get(user_id)
        if not ws:
            return None
        return {
            "employee_id": ws.employee_id,
            "employee_display_name": ws.employee_display_name,
            "schedule_name": ws.schedule_name,
            "hours_per_week": ws.hours_per_week,
            "days_per_week": ws.days_per_week,
            "work_days": [
                {"day": d.day_of_week, "start": d.start_time, "end": d.end_time, "hours": d.hours}
                for d in ws.work_days
            ],
        }
