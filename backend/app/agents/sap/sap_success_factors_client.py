from __future__ import annotations

from urllib.parse import quote, urlencode

import httpx

from app.agents.sap.absence_formatter import normalize_employee_absences
from app.agents.sap.absence_schemas import EmployeeAbsence
from app.config.settings import Settings
from app.services.errors import ConnectorUnavailableError


class SapSuccessFactorsClient:
    def __init__(
        self,
        *,
        settings: Settings,
        auth_service,
        client: httpx.AsyncClient | None = None,
    ):
        self._settings = settings
        self._auth_service = auth_service
        self._client = client or httpx.AsyncClient(timeout=settings.connector_timeout_seconds)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def build_employee_absences_url(self, *, user_id: str, start_date: str, end_date: str) -> str:
        self._ensure_base_url()
        sap_filter = (
            f"userId eq '{_escape_odata_string(user_id)}' "
            f"and startDate ge datetime'{start_date}T00:00:00' "
            f"and endDate le datetime'{end_date}T23:59:59'"
        )
        query = urlencode(
            {"$format": "json", "$filter": sap_filter, "$expand": "timeTypeNav"},
            quote_via=quote,
        )
        return f"{self._settings.sap_base_url.rstrip('/')}/EmployeeTime?{query}"

    def build_absences_url(self, *, start_date: str, end_date: str) -> str:
        self._ensure_base_url()
        sap_filter = (
            f"startDate le datetime'{end_date}T23:59:59' "
            f"and endDate ge datetime'{start_date}T00:00:00'"
        )
        query = urlencode(
            {"$format": "json", "$filter": sap_filter, "$expand": "timeTypeNav"},
            quote_via=quote,
        )
        return f"{self._settings.sap_base_url.rstrip('/')}/EmployeeTime?{query}"

    def build_user_lookup_url(self, *, first_name: str, last_name: str) -> str:
        self._ensure_base_url()
        sap_filter = (
            f"firstName eq '{_escape_odata_string(first_name)}' "
            f"and lastName eq '{_escape_odata_string(last_name)}'"
        )
        query = urlencode({"$format": "json", "$filter": sap_filter}, quote_via=quote)
        return f"{self._settings.sap_base_url.rstrip('/')}/User?{query}"

    async def get_employee_absences(self, *, user_id: str, start_date: str, end_date: str) -> list[EmployeeAbsence]:
        url = self.build_employee_absences_url(user_id=user_id, start_date=start_date, end_date=end_date)
        payload = await self._get_all_pages_json(url)
        return normalize_employee_absences(payload)

    async def get_absences(self, *, start_date: str, end_date: str) -> list[EmployeeAbsence]:
        url = self.build_absences_url(start_date=start_date, end_date=end_date)
        payload = await self._get_all_pages_json(url)
        return normalize_employee_absences(payload)

    def build_employee_department_url(self, *, user_id: str) -> str:
        self._ensure_base_url()
        sap_filter = f"userId eq '{_escape_odata_string(user_id)}'"
        query = urlencode(
            {"$format": "json", "$filter": sap_filter, "$orderby": "startDate desc", "$top": "1", "$select": "userId,department"},
            quote_via=quote,
        )
        return f"{self._settings.sap_base_url.rstrip('/')}/EmpJob?{query}"

    def build_department_employees_url(self, *, department: str) -> str:
        self._ensure_base_url()
        sap_filter = f"department eq '{_escape_odata_string(department)}'"
        query = urlencode(
            {"$format": "json", "$filter": sap_filter, "$select": "userId,department"},
            quote_via=quote,
        )
        return f"{self._settings.sap_base_url.rstrip('/')}/EmpJob?{query}"

    async def get_employee_department(self, *, user_id: str) -> str | None:
        url = self.build_employee_department_url(user_id=user_id)
        try:
            payload = await self._get_json(url)
        except ConnectorUnavailableError:
            return None
        results = payload.get("d", {}).get("results", [])
        if not isinstance(results, list) or not results:
            return None
        dept = results[0].get("department")
        return str(dept).strip() if dept else None

    async def get_department_employees(self, *, department: str) -> list[str]:
        url = self.build_department_employees_url(department=department)
        try:
            payload = await self._get_all_pages_json(url)
        except ConnectorUnavailableError:
            return []
        results = payload.get("d", {}).get("results", [])
        if not isinstance(results, list):
            return []
        seen: set[str] = set()
        user_ids: list[str] = []
        for r in results:
            uid = r.get("userId")
            if uid and str(uid) not in seen:
                seen.add(str(uid))
                user_ids.append(str(uid))
        return user_ids

    async def resolve_user_id_by_name(self, employee_name: str) -> str | None:
        parts = employee_name.title().split()
        if len(parts) < 2:
            return None
        first_name = parts[0]
        last_name = " ".join(parts[1:])
        url = self.build_user_lookup_url(first_name=first_name, last_name=last_name)
        payload = await self._get_json(url)
        results = payload.get("d", {}).get("results", []) if isinstance(payload, dict) else []
        if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
            return None
        user_id = results[0].get("userId")
        return str(user_id) if user_id else None

    async def _get_json(self, url: str) -> dict:
        token = await self._auth_service.get_access_token()
        try:
            response = await self._client.get(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                raise ConnectorUnavailableError("SAP API authorization failed.") from exc
            raise ConnectorUnavailableError("SAP API request failed.") from exc
        except httpx.TimeoutException as exc:
            raise ConnectorUnavailableError("SAP API request timed out.") from exc
        except httpx.TransportError as exc:
            raise ConnectorUnavailableError("SAP API request failed: endpoint unavailable.") from exc
        except ValueError as exc:
            raise ConnectorUnavailableError("SAP API returned malformed data.") from exc
        if not isinstance(payload, dict):
            raise ConnectorUnavailableError("SAP API returned malformed data.")
        return payload

    async def _get_all_pages_json(self, url: str) -> dict:
        all_results: list = []
        next_url: str | None = url
        page_count = 0
        max_pages = 100

        while next_url:
            page_count += 1
            if page_count > max_pages:
                raise ConnectorUnavailableError("SAP API pagination exceeded the configured safety limit.")
            payload = await self._get_json(next_url)
            page_data = payload.get("d")
            if not isinstance(page_data, dict):
                return payload if page_count == 1 else {"d": {"results": all_results}}
            results = page_data.get("results")
            if not isinstance(results, list):
                return payload if page_count == 1 else {"d": {"results": all_results}}
            all_results.extend(results)
            raw_next = page_data.get("__next")
            next_url = raw_next if isinstance(raw_next, str) and raw_next else None

        return {"d": {"results": all_results}}

    def _ensure_base_url(self) -> None:
        if not self._settings.sap_base_url:
            raise ConnectorUnavailableError("SAP_BASE_URL is not configured.")


def _escape_odata_string(value: str) -> str:
    return value.replace("'", "''")
