from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.schemas.domain import AbsenceRecord, Employee


class SuccessFactorsConnector(ABC):
    backend_name: str

    @abstractmethod
    async def search_employees(self, reference: str) -> list[Employee]:
        raise NotImplementedError

    @abstractmethod
    async def get_employee(self, employee_id: str) -> Employee | None:
        raise NotImplementedError

    @abstractmethod
    async def list_absences(
        self,
        employee_id: str,
        start_date: date,
        end_date: date,
        absence_type: str | None = None,
    ) -> list[AbsenceRecord]:
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> tuple[bool, str]:
        raise NotImplementedError
