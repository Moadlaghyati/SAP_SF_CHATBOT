from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

import httpx

from app.agents.sap.absence_formatter import normalize_employee_absences
from app.agents.sap.absence_schemas import EmployeeAbsence
from app.config.settings import Settings
from app.services.errors import ConnectorUnavailableError

LOGGER = logging.getLogger(__name__)

import re as _re

def _parse_sap_date(value: object) -> str | None:
    """Convert SAP OData v2 /Date(ms)/ format to YYYY-MM-DD ISO string."""
    if not value:
        return None
    if isinstance(value, str):
        m = _re.match(r"/Date\((-?\d+)\)/", value)
        if m:
            ms = int(m.group(1))
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        return value  # already ISO or unknown — return as-is
    return str(value)


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
        # Overlap filter: returns absences that overlap the requested period,
        # including ones that start before or end after the range boundaries.
        sap_filter = (
            f"userId eq '{_escape_odata_string(user_id)}' "
            f"and startDate le datetime'{end_date}T23:59:59' "
            f"and endDate ge datetime'{start_date}T00:00:00'"
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
        LOGGER.debug("[SAP] get_employee_absences url=%s", url)
        payload = await self._get_all_pages_json(url)
        raw_results = payload.get("d", {}).get("results", [])
        LOGGER.debug("[SAP] get_employee_absences raw_record_count=%d user_id=%s", len(raw_results), user_id)
        for i, r in enumerate(raw_results[:5]):
            LOGGER.debug("[SAP] raw[%d] timeType=%s startDate=%s endDate=%s timeTypeNav=%s",
                        i, r.get("timeType"), r.get("startDate"), r.get("endDate"),
                        r.get("timeTypeNav"))
        normalized = normalize_employee_absences(payload)
        LOGGER.debug("[SAP] get_employee_absences normalized_count=%d", len(normalized))
        return normalized

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

    def build_direct_reports_url(self, *, manager_user_id: str) -> str:
        self._ensure_base_url()
        sap_filter = f"managerId eq '{_escape_odata_string(manager_user_id)}'"
        query = urlencode(
            {"$format": "json", "$filter": sap_filter, "$select": "userId,managerId,startDate,endDate"},
            quote_via=quote,
        )
        return f"{self._settings.sap_base_url.rstrip('/')}/EmpJob?{query}"

    async def _resolve_manager_sap_user_id(self, numeric_id: str, display_name: str | None) -> str:
        """Convert a numeric employee ID to the alphanumeric SAP userId used in EmpJob.managerId."""
        # Check if numeric_id is already a valid userId in the User entity
        try:
            url = self.build_user_by_id_url(user_id=numeric_id)
            payload = await self._get_json(url)
            results = payload.get("d", {}).get("results", [])
            if isinstance(results, list) and results:
                return numeric_id  # numeric ID is the SAP userId — use as-is
        except Exception:
            pass

        # Numeric ID not found in User entity — resolve via full name
        if display_name:
            try:
                resolved = await self.resolve_user_id_by_name(display_name)
                if resolved:
                    return resolved
            except Exception:
                pass

        return numeric_id  # best-effort fallback

    async def get_direct_report_user_ids(
        self, *, manager_user_id: str, manager_display_name: str | None = None
    ) -> list[str]:
        resolved_id = await self._resolve_manager_sap_user_id(manager_user_id, manager_display_name)
        url = self.build_direct_reports_url(manager_user_id=resolved_id)
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

    def build_user_by_id_url(self, *, user_id: str) -> str:
        self._ensure_base_url()
        sap_filter = f"userId eq '{_escape_odata_string(user_id)}'"
        query = urlencode(
            {"$format": "json", "$filter": sap_filter, "$select": "userId,firstName,lastName"},
            quote_via=quote,
        )
        return f"{self._settings.sap_base_url.rstrip('/')}/User?{query}"

    def build_per_personal_url(self, *, person_id: str) -> str:
        self._ensure_base_url()
        sap_filter = f"personIdExternal eq '{_escape_odata_string(person_id)}'"
        query = urlencode(
            {"$format": "json", "$filter": sap_filter, "$select": "personIdExternal,firstName,lastName", "$top": "1"},
            quote_via=quote,
        )
        return f"{self._settings.sap_base_url.rstrip('/')}/PerPersonal?{query}"

    async def _resolve_one_display_name(self, user_id: str) -> str | None:
        # Try User entity first
        url = self.build_user_by_id_url(user_id=user_id)
        try:
            payload = await self._get_json(url)
            results = payload.get("d", {}).get("results", [])
            if isinstance(results, list) and results and isinstance(results[0], dict):
                first = str(results[0].get("firstName") or "").strip()
                last = str(results[0].get("lastName") or "").strip()
                display = f"{first} {last}".strip()
                if display:
                    return display
        except Exception:
            pass

        # Fallback: PerPersonal entity (handles numeric personIdExternal IDs)
        url = self.build_per_personal_url(person_id=user_id)
        try:
            payload = await self._get_json(url)
            results = payload.get("d", {}).get("results", [])
            if isinstance(results, list) and results and isinstance(results[0], dict):
                first = str(results[0].get("firstName") or "").strip()
                last = str(results[0].get("lastName") or "").strip()
                display = f"{first} {last}".strip()
                if display:
                    return display
        except Exception:
            pass

        return None

    async def get_display_names_for_user_ids(self, user_ids: list[str]) -> dict[str, str]:
        if not user_ids:
            return {}
        names: dict[str, str] = {}
        for uid in user_ids:
            display = await self._resolve_one_display_name(uid)
            if display:
                names[uid] = display
        return names

    async def resolve_user_id_by_name(self, employee_name: str) -> str | None:
        parts = employee_name.title().split()
        if len(parts) < 2:
            return None
        first_name = parts[0]
        last_name = " ".join(parts[1:])
        url = self.build_user_lookup_url(first_name=first_name, last_name=last_name)
        LOGGER.debug("[SAP] resolve_user_id_by_name name=%r url=%s", employee_name, url)
        payload = await self._get_json(url)
        results = payload.get("d", {}).get("results", []) if isinstance(payload, dict) else []
        LOGGER.debug("[SAP] resolve_user_id_by_name name=%r result_count=%d results=%s",
                    employee_name, len(results) if isinstance(results, list) else -1,
                    [r.get("userId") for r in results if isinstance(r, dict)][:5])
        if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
            return None
        user_id = results[0].get("userId")
        LOGGER.debug("[SAP] resolve_user_id_by_name name=%r resolved_user_id=%s", employee_name, user_id)
        return str(user_id) if user_id else None

    def build_user_job_title_url(self, *, user_id: str) -> str:
        self._ensure_base_url()
        sap_filter = f"userId eq '{_escape_odata_string(user_id)}'"
        query = urlencode(
            {"$format": "json", "$filter": sap_filter, "$select": "userId,jobTitle", "$top": "1", "$orderby": "startDate desc"},
            quote_via=quote,
        )
        return f"{self._settings.sap_base_url.rstrip('/')}/EmpJob?{query}"

    async def get_user_job_title(self, user_id: str) -> str | None:
        url = self.build_user_job_title_url(user_id=user_id)
        try:
            payload = await self._get_json(url)
        except ConnectorUnavailableError:
            return None
        results = payload.get("d", {}).get("results", [])
        if not isinstance(results, list) or not results:
            return None
        title = results[0].get("jobTitle")
        return str(title).strip() if title else None

    def build_emp_job_by_person_id_url(self, *, person_id: str) -> str:
        self._ensure_base_url()
        sap_filter = f"personIdExternal eq '{_escape_odata_string(person_id)}'"
        query = urlencode(
            {"$format": "json", "$filter": sap_filter, "$select": "userId,personIdExternal", "$top": "1"},
            quote_via=quote,
        )
        return f"{self._settings.sap_base_url.rstrip('/')}/EmpJob?{query}"

    async def resolve_user_id_by_person_id(self, *, person_id: str) -> str | None:
        """Look up the SAP userId from a numeric personIdExternal via EmpJob."""
        url = self.build_emp_job_by_person_id_url(person_id=person_id)
        LOGGER.debug("[SAP] resolve_user_id_by_person_id person_id=%s url=%s", person_id, url)
        try:
            payload = await self._get_json(url)
        except ConnectorUnavailableError:
            return None
        results = payload.get("d", {}).get("results", [])
        if not isinstance(results, list) or not results or not isinstance(results[0], dict):
            return None
        user_id = results[0].get("userId")
        LOGGER.debug("[SAP] resolve_user_id_by_person_id person_id=%s -> userId=%s", person_id, user_id)
        return str(user_id) if user_id else None

    def build_all_users_url(self) -> str:
        self._ensure_base_url()
        query = urlencode(
            {"$format": "json", "$select": "userId,firstName,lastName"},
            quote_via=quote,
        )
        return f"{self._settings.sap_base_url.rstrip('/')}/User?{query}"

    async def fetch_all_user_ids(self) -> list[str]:
        url = self.build_all_users_url()
        LOGGER.info("[SAP] fetch_all_user_ids fetching all SAP users from %s", url)
        try:
            payload = await self._get_all_pages_json(url)
        except ConnectorUnavailableError as exc:
            LOGGER.warning("[SAP] fetch_all_user_ids failed: %s", exc)
            return []
        results = payload.get("d", {}).get("results", [])
        if not isinstance(results, list):
            return []
        user_ids = [str(r["userId"]) for r in results if isinstance(r, dict) and r.get("userId")]
        LOGGER.info("[SAP] fetch_all_user_ids resolved %d SAP users", len(user_ids))
        return user_ids

    async def verify_user_id_exists(self, user_id: str) -> bool:
        """Return True if user_id is a valid SAP userId in the User entity."""
        url = self.build_user_by_id_url(user_id=user_id)
        LOGGER.debug("[SAP] verify_user_id_exists user_id=%s url=%s", user_id, url)
        try:
            payload = await self._get_json(url)
            results = payload.get("d", {}).get("results", [])
            exists = isinstance(results, list) and len(results) > 0
            LOGGER.debug("[SAP] verify_user_id_exists user_id=%s exists=%s", user_id, exists)
            return exists
        except Exception:
            return False

    async def get_time_types(self) -> list[dict]:
        """Fetch active ABSENCE TimeType codes from SAP."""
        self._ensure_base_url()
        query = urlencode(
            {"$format": "json",
             "$select": "externalCode,externalName_en_US,externalName_defaultValue,category,unit,mdfSystemStatus",
             "$top": "100"},
            quote_via=quote,
        )
        url = f"{self._settings.sap_base_url.rstrip('/')}/TimeType?{query}"
        try:
            payload = await self._get_json(url)
        except ConnectorUnavailableError:
            return []
        results = payload.get("d", {}).get("results", [])
        if not isinstance(results, list):
            return []
        types = [
            {
                "code": r.get("externalCode"),
                "name": r.get("externalName_en_US") or r.get("externalName_defaultValue") or r.get("externalCode"),
                "unit": r.get("unit"),
            }
            for r in results
            if isinstance(r, dict)
            and r.get("mdfSystemStatus") == "A"
            and r.get("category") == "ABSENCE"
            and r.get("externalCode")
        ]
        # Prefer Morocco-specific codes (MA_ / MAR_ prefix) for this instance
        ma_types = [t for t in types if str(t["code"]).startswith(("MA_", "MAR_"))]
        return ma_types if ma_types else types

    async def post_time_off_request(
        self, *, user_id: str, time_type: str, start_date: str, end_date: str,
        external_code: str | None = None, attachment_id: int | None = None,
    ) -> dict:
        """POST a new EmployeeTime record to SAP SuccessFactors."""
        self._ensure_base_url()
        url = f"{self._settings.sap_base_url.rstrip('/')}/EmployeeTime"

        def _to_sap_date(iso_date: str) -> str:
            dt = datetime.strptime(iso_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return f"/Date({int(dt.timestamp() * 1000)})/"

        if not external_code:
            external_code = f"CHAT_{uuid.uuid4().hex[:12].upper()}"
        pl_key = (
            "PickListValueV2("
            "PickListV2_effectiveStartDate=datetime'1900-01-01T00:00:00',"
            "PickListV2_id='sicknessReason',"
            "externalCode='1')"
        )
        body = {
            "userId": user_id,
            "timeType": time_type,
            "startDate": _to_sap_date(start_date),
            "endDate": _to_sap_date(end_date),
            "externalCode": external_code,
            "cust_fitNote": attachment_id is not None,
            "cust_reason": "1",
            "timeTypeNav": {"__metadata": {"uri": f"TimeType('{time_type}')"}},
            "userIdNav": {"__metadata": {"uri": f"User('{user_id}')"}},
            "cust_reasonNav": {"__metadata": {"uri": pl_key}},
        }
        if attachment_id is not None:
            base = self._settings.sap_base_url.rstrip("/")
            body["cust_attachmentNav"] = {"__metadata": {"uri": f"{base}/Attachment({attachment_id})"}}
        token = await self._auth_service.get_access_token()
        try:
            response = await self._client.post(
                url,
                json=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return {"externalCode": external_code}
        except httpx.HTTPStatusError as exc:
            try:
                err_body = exc.response.json()
                err_msg = err_body.get("error", {}).get("message", {}).get("value", exc.response.text)
            except Exception:
                err_msg = exc.response.text
            if exc.response.status_code in {401, 403}:
                raise ConnectorUnavailableError("SAP API authorization failed.") from exc
            raise ConnectorUnavailableError(f"SAP request failed: {err_msg}") from exc
        except httpx.TimeoutException as exc:
            raise ConnectorUnavailableError("SAP API request timed out.") from exc
        except httpx.TransportError as exc:
            raise ConnectorUnavailableError("SAP API request failed: endpoint unavailable.") from exc

    async def upload_attachment(
        self,
        *,
        file_bytes: bytes,
        file_name: str,
        mime_type: str,
        user_id: str,
        document_entity_id: str,
    ) -> int:
        """Upload a file to SAP Attachment entity and return the attachmentId.

        document_entity_id should be the externalCode that will be used for the
        EmployeeTime record so SAP can link attachment → time-off request.
        """
        self._ensure_base_url()
        import base64
        url = f"{self._settings.sap_base_url.rstrip('/')}/Attachment"
        body = {
            "fileName": file_name,
            "fileContent": base64.b64encode(file_bytes).decode("ascii"),
            "module": self._settings.sap_attachment_module,
            "documentEntityId": document_entity_id,
            "userId": user_id,
            "deletable": True,
            "viewable": True,
        }
        token = await self._auth_service.get_access_token()
        try:
            response = await self._client.post(
                url,
                json=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )
            response.raise_for_status()
            data = response.json()
            attachment_id = (
                data.get("d", {}).get("attachmentId")
                or data.get("attachmentId")
            )
            if attachment_id is None:
                raise ConnectorUnavailableError("SAP attachment upload succeeded but returned no attachmentId.")
            return int(attachment_id)
        except httpx.HTTPStatusError as exc:
            try:
                err_body = exc.response.json()
                err_msg = err_body.get("error", {}).get("message", {}).get("value", exc.response.text)
            except Exception:
                err_msg = exc.response.text
            if exc.response.status_code in {401, 403}:
                raise ConnectorUnavailableError("SAP API authorization failed.") from exc
            raise ConnectorUnavailableError(f"SAP attachment upload failed: {err_msg}") from exc
        except httpx.TimeoutException as exc:
            raise ConnectorUnavailableError("SAP attachment upload timed out.") from exc
        except httpx.TransportError as exc:
            raise ConnectorUnavailableError("SAP attachment upload failed: endpoint unavailable.") from exc

    async def get_leave_balance(self, *, user_id: str) -> list[dict]:
        """Fetch EmpTimeAccountBalance for a user."""
        self._ensure_base_url()
        sap_filter = f"userId eq '{_escape_odata_string(user_id)}'"
        query = urlencode(
            {"$format": "json", "$filter": sap_filter,
             "$select": "userId,timeAccountType,balance,unit,bookingStartDate,bookingEndDate"},
            quote_via=quote,
        )
        url = f"{self._settings.sap_base_url.rstrip('/')}/EmpTimeAccountBalance?{query}"
        LOGGER.debug("[SAP] get_leave_balance user_id=%s", user_id)
        try:
            payload = await self._get_json(url)
        except ConnectorUnavailableError as exc:
            LOGGER.warning("[SAP] get_leave_balance failed: %s", exc)
            return []
        results = payload.get("d", {}).get("results", [])
        if not isinstance(results, list):
            return []
        return [
            {
                "accountType": r.get("timeAccountType"),
                "balance": r.get("balance"),
                "unit": r.get("unit", "day(s)"),
                "bookingStart": r.get("bookingStartDate"),
                "bookingEnd": r.get("bookingEndDate"),
            }
            for r in results
            if isinstance(r, dict)
        ]

    async def get_pending_leave_requests(self, *, user_id: str) -> list[dict]:
        """Fetch pending EmployeeTime records for a user."""
        self._ensure_base_url()
        sap_filter = (
            f"userId eq '{_escape_odata_string(user_id)}' "
            f"and approvalStatus eq 'PENDING'"
        )
        query = urlencode(
            {"$format": "json", "$filter": sap_filter,
             "$select": "userId,timeType,startDate,endDate,quantityInDays,approvalStatus,externalCode"},
            quote_via=quote,
        )
        url = f"{self._settings.sap_base_url.rstrip('/')}/EmployeeTime?{query}"
        LOGGER.debug("[SAP] get_pending_leave_requests user_id=%s", user_id)
        try:
            payload = await self._get_json(url)
        except ConnectorUnavailableError as exc:
            LOGGER.warning("[SAP] get_pending_leave_requests failed: %s", exc)
            return []
        results = payload.get("d", {}).get("results", [])
        if not isinstance(results, list):
            return []
        return [
            {
                "timeType": r.get("timeType"),
                "startDate": _parse_sap_date(r.get("startDate")),
                "endDate": _parse_sap_date(r.get("endDate")),
                "quantityInDays": r.get("quantityInDays"),
                "approvalStatus": r.get("approvalStatus"),
                "externalCode": r.get("externalCode"),
            }
            for r in results
            if isinstance(r, dict)
        ]

    async def get_holidays(self, *, start_date: str, end_date: str) -> list[dict]:
        """Fetch Holiday records for a date range.

        Tries the SAP Holiday entity first; falls back to the built-in Morocco
        public holiday calendar when the entity is unavailable in this instance.
        """
        self._ensure_base_url()
        sap_filter = (
            f"holidayDate ge datetime'{start_date}T00:00:00' "
            f"and holidayDate le datetime'{end_date}T23:59:59'"
        )
        query = urlencode(
            {"$format": "json", "$filter": sap_filter,
             "$select": "holidayDate,name_defaultValue,name_en_US,holidayClass"},
            quote_via=quote,
        )
        url = f"{self._settings.sap_base_url.rstrip('/')}/Holiday?{query}"
        LOGGER.debug("[SAP] get_holidays start=%s end=%s", start_date, end_date)
        try:
            payload = await self._get_all_pages_json(url)
            results = payload.get("d", {}).get("results", [])
            if isinstance(results, list) and results:
                holidays = []
                for r in results:
                    if not isinstance(r, dict):
                        continue
                    h_date = _parse_sap_date(r.get("holidayDate")) or r.get("holidayDate", "")
                    name = r.get("name_en_US") or r.get("name_defaultValue") or "Public Holiday"
                    holidays.append({"date": h_date, "name": name, "type": r.get("holidayClass", "public")})
                holidays.sort(key=lambda h: h["date"])
                return holidays
        except ConnectorUnavailableError as exc:
            LOGGER.warning("[SAP] get_holidays SAP entity unavailable, using built-in calendar: %s", exc)

        # Fallback: built-in Morocco public holiday calendar
        from datetime import date as _date
        from app.connectors.mock_data import MOCK_HOLIDAYS
        start = _date.fromisoformat(start_date)
        end = _date.fromisoformat(end_date)
        return [
            {"date": h.date, "name": h.name, "type": h.type}
            for h in MOCK_HOLIDAYS
            if start <= _date.fromisoformat(h.date) <= end
        ]

    async def get_work_schedule(self, *, user_id: str) -> dict | None:
        """Fetch work schedule for an employee via EmpJob workSchedule field.

        Falls back to the standard Morocco 40h/week schedule when SAP returns nothing.
        """
        self._ensure_base_url()
        sap_filter = f"userId eq '{_escape_odata_string(user_id)}'"
        query = urlencode(
            {"$format": "json", "$filter": sap_filter,
             "$select": "userId,workSchedule", "$orderby": "startDate desc", "$top": "1",
             "$expand": "workScheduleNav"},
            quote_via=quote,
        )
        url = f"{self._settings.sap_base_url.rstrip('/')}/EmpJob?{query}"
        LOGGER.debug("[SAP] get_work_schedule user_id=%s", user_id)
        sap_result = None
        try:
            payload = await self._get_json(url)
            results = payload.get("d", {}).get("results", [])
            if isinstance(results, list) and results:
                job = results[0]
                ws_nav = job.get("workScheduleNav") or {}
                if isinstance(ws_nav, dict) and ws_nav.get("results"):
                    ws_nav = ws_nav["results"][0] if ws_nav["results"] else ws_nav
                ws_name = (ws_nav.get("name_defaultValue") or ws_nav.get("name_en_US")
                           or job.get("workSchedule") or "Standard")
                hours_per_day = float(ws_nav.get("hoursPerDay") or 8)
                work_days_count = int(ws_nav.get("workDays") or 5)
                sap_result = {
                    "employee_id": user_id,
                    "schedule_name": ws_name,
                    "hours_per_week": hours_per_day * work_days_count,
                    "days_per_week": work_days_count,
                    "work_days": [
                        {"day": d, "start": "08:30", "end": "17:30", "hours": hours_per_day}
                        for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][:work_days_count]
                    ],
                }
        except ConnectorUnavailableError as exc:
            LOGGER.warning("[SAP] get_work_schedule failed: %s", exc)

        if sap_result:
            return sap_result

        # Fallback: standard Morocco 40h/week schedule
        LOGGER.info("[SAP] get_work_schedule using built-in schedule for user_id=%s", user_id)
        from app.connectors.mock_data import MOCK_EMPLOYEES
        display_name = next(
            (e.display_name for e in MOCK_EMPLOYEES
             if e.employee_id == user_id or getattr(e, "sap_user_id", None) == user_id),
            user_id,
        )
        return {
            "employee_id": user_id,
            "employee_display_name": display_name,
            "schedule_name": "Standard Morocco (40h/week)",
            "hours_per_week": 40.0,
            "days_per_week": 5,
            "work_days": [
                {"day": "Monday",    "start": "08:30", "end": "17:30", "hours": 8.0},
                {"day": "Tuesday",   "start": "08:30", "end": "17:30", "hours": 8.0},
                {"day": "Wednesday", "start": "08:30", "end": "17:30", "hours": 8.0},
                {"day": "Thursday",  "start": "08:30", "end": "17:30", "hours": 8.0},
                {"day": "Friday",    "start": "08:30", "end": "17:00", "hours": 8.0},
            ],
        }

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
