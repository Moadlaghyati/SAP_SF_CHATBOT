from __future__ import annotations

import asyncio
from datetime import date

from app.connectors.base import SuccessFactorsConnector
from app.connectors.mock_data import MOCK_ABSENCES, MOCK_EMPLOYEES
from app.schemas.domain import AbsenceRecord, Employee


def _normalize_token(value: str) -> str:
    return " ".join(value.lower().replace(".", " ").replace("'", " ").split())


class MockSuccessFactorsConnector(SuccessFactorsConnector):
    backend_name = "mock"

    def __init__(self, latency_ms: int = 0):
        self._latency_ms = max(latency_ms, 0)
        self._employees = list(MOCK_EMPLOYEES)
        self._absences = list(MOCK_ABSENCES)

    async def _sleep(self) -> None:
        if self._latency_ms:
            await asyncio.sleep(self._latency_ms / 1000)

    async def search_employees(self, reference: str) -> list[Employee]:
        await self._sleep()
        normalized_reference = _normalize_token(
            reference.replace("my direct report", "").replace("direct report", "").strip()
        )
        if not normalized_reference:
            return []

        matches: list[Employee] = []
        for employee in self._employees:
            candidates = [
                employee.display_name,
                employee.first_name,
                employee.last_name,
                employee.employee_id,
                *employee.aliases,
            ]
            if any(normalized_reference in _normalize_token(candidate) for candidate in candidates):
                matches.append(employee)

        exact_name_matches = [
            employee
            for employee in matches
            if normalized_reference == _normalize_token(employee.display_name)
            or normalized_reference == _normalize_token(employee.employee_id)
        ]
        return exact_name_matches or matches

    async def get_employee(self, employee_id: str) -> Employee | None:
        await self._sleep()
        for employee in self._employees:
            if employee.employee_id == employee_id:
                return employee
        return None

    async def list_absences(
        self,
        employee_id: str,
        start_date: date,
        end_date: date,
        absence_type: str | None = None,
    ) -> list[AbsenceRecord]:
        await self._sleep()
        filtered = [
            absence
            for absence in self._absences
            if absence.employee_id == employee_id
            and absence.start_date >= start_date
            and absence.end_date <= end_date
        ]
        if absence_type:
            normalized_absence_type = _normalize_token(absence_type)
            filtered = [
                absence
                for absence in filtered
                if _normalize_token(absence.absence_type) == normalized_absence_type
            ]
        return sorted(filtered, key=lambda item: (item.start_date, item.absence_id))

    async def health_check(self) -> tuple[bool, str]:
        return True, "Mock SuccessFactors connector is ready."
