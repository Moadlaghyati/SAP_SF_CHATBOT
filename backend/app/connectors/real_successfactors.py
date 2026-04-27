from __future__ import annotations

from datetime import date

import httpx

from app.config.settings import Settings
from app.connectors.base import SuccessFactorsConnector
from app.schemas.domain import AbsenceRecord, Employee
from app.services.errors import ConnectorUnavailableError


class RealSuccessFactorsConnector(SuccessFactorsConnector):
    backend_name = "successfactors"

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = httpx.AsyncClient(timeout=settings.connector_timeout_seconds)

    async def close(self) -> None:
        await self._client.aclose()

    def _ensure_configured(self) -> None:
        if not self._settings.sap_base_url:
            raise ConnectorUnavailableError(
                "SAP SuccessFactors connector is selected, but SAP_BASE_URL is not configured."
            )
        if self._settings.sap_auth_mode == "basic" and (
            not self._settings.sap_username or not self._settings.sap_password
        ):
            raise ConnectorUnavailableError(
                "SAP basic authentication is selected, but SAP_USERNAME or SAP_PASSWORD is missing."
            )
        if self._settings.sap_auth_mode == "oauth" and not self._has_supported_oauth_config():
            raise ConnectorUnavailableError(
                "SAP OAuth is selected, but OAuth credentials are incomplete."
            )

    def _has_supported_oauth_config(self) -> bool:
        has_client_credentials = bool(self._settings.sap_client_id and self._settings.sap_client_secret)
        has_saml_bearer = bool(
            self._settings.sap_client_id
            and self._settings.sap_company_id
            and self._settings.sap_oauth_token_url
            and self._settings.sap_saml_assertion
        )
        return has_client_credentials or has_saml_bearer

    async def search_employees(self, reference: str) -> list[Employee]:
        self._ensure_configured()
        # TODO: Call the SuccessFactors OData User or PerPerson endpoint with a
        # select clause limited to identifiers and display fields only.
        # TODO: Apply the filter server-side, then normalize the payload into Employee.
        raise ConnectorUnavailableError(
            "Real SAP employee lookup is scaffolded but not implemented yet."
        )

    async def get_employee(self, employee_id: str) -> Employee | None:
        self._ensure_configured()
        # TODO: Fetch a single employee with a narrow select list and normalize it.
        raise ConnectorUnavailableError(
            "Real SAP employee lookup by ID is scaffolded but not implemented yet."
        )

    async def list_absences(
        self,
        employee_id: str,
        start_date: date,
        end_date: date,
        absence_type: str | None = None,
    ) -> list[AbsenceRecord]:
        self._ensure_configured()
        # TODO: Call EmployeeTime or the appropriate absence entity using OData filters:
        # employee_id eq '{employee_id}' and startDate ge ... and endDate le ...
        # TODO: Apply $select to only the fields required for AbsenceRecord.
        # TODO: Map the SAP payload into normalized AbsenceRecord objects.
        _ = (employee_id, start_date, end_date, absence_type)
        raise ConnectorUnavailableError(
            "Real SAP absence retrieval is scaffolded but not implemented yet."
        )

    async def health_check(self) -> tuple[bool, str]:
        try:
            self._ensure_configured()
        except ConnectorUnavailableError as exc:
            return False, str(exc)
        return True, "SuccessFactors configuration is present. Real SAP absence requests are handled by the dedicated SAP Absence Agent."
