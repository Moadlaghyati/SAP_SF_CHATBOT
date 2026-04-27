from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.connectors.base import SuccessFactorsConnector
from app.repositories.request_repository import RequestRepository
from app.schemas.domain import AbsenceSummary, AbsenceTypeBreakdown, Employee, Period, RequestContext


class ToolService:
    def __init__(self, connector: SuccessFactorsConnector, request_repository: RequestRepository):
        self._connector = connector
        self._request_repository = request_repository

    @property
    def connector_backend(self) -> str:
        return self._connector.backend_name

    async def resolve_employee(self, reference: str, requester_context: RequestContext) -> list[Employee]:
        normalized_reference = reference.strip().lower()
        if normalized_reference in {"me", "myself", "my own data", "my data"} and requester_context.employee_id:
            employee = await self._connector.get_employee(requester_context.employee_id)
            return [employee] if employee else []
        return await self._connector.search_employees(reference)

    async def count_absences(
        self,
        employee_id: str,
        start_date: date,
        end_date: date,
        absence_type: str | None = None,
    ) -> AbsenceSummary:
        records = await self._connector.list_absences(employee_id, start_date, end_date, absence_type)
        employee = await self._connector.get_employee(employee_id)
        breakdown_map: dict[str, dict[str, float]] = defaultdict(lambda: {"count": 0, "days": 0.0})

        for record in records:
            breakdown_map[record.absence_type]["count"] += 1
            breakdown_map[record.absence_type]["days"] += record.days

        by_type = [
            AbsenceTypeBreakdown(type=absence_type_name, count=int(values["count"]), days=values["days"])
            for absence_type_name, values in sorted(breakdown_map.items())
        ]

        return AbsenceSummary(
            employee_id=employee_id,
            employee_display_name=employee.display_name if employee else employee_id,
            period=Period(start=start_date, end=end_date),
            absence_count=len(records),
            absence_days=sum(record.days for record in records),
            by_type=by_type,
        )

    async def list_absences(
        self,
        employee_id: str,
        start_date: date,
        end_date: date,
        limit: int = 20,
    ):
        records = await self._connector.list_absences(employee_id, start_date, end_date, None)
        return records[:limit]

    async def health_check(self) -> tuple[bool, str]:
        return await self._connector.health_check()

    def get_demo_trace(self, request_id: str):
        return self._request_repository.get_trace(request_id)
