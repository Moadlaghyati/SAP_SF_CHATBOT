from __future__ import annotations

import time
from typing import Any

import httpx

from app.config.settings import Settings
from app.services.errors import ConnectorUnavailableError


class SapAuthService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.connector_timeout_seconds)
        self._owns_client = client is None
        self._cached_token: str | None = None
        self._expires_at_epoch: float = 0.0

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_access_token(self) -> str:
        if self._cached_token and time.time() < self._expires_at_epoch - 60:
            return self._cached_token

        self._ensure_configured()
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:saml2-bearer",
            "client_id": self._settings.sap_client_id,
            "company_id": self._settings.sap_company_id,
            "assertion": self._settings.sap_saml_assertion,
        }

        try:
            response = await self._client.post(
                self._settings.sap_oauth_token_url,
                data=data,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in {401, 403}:
                raise ConnectorUnavailableError("SAP token fetch failed: authorization was rejected.") from exc
            raise ConnectorUnavailableError("SAP token fetch failed.") from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ConnectorUnavailableError("SAP token fetch failed: token endpoint is unavailable.") from exc
        except ValueError as exc:
            raise ConnectorUnavailableError("SAP token fetch failed: malformed token response.") from exc

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ConnectorUnavailableError("SAP token fetch failed: access token missing from response.")

        expires_in = payload.get("expires_in", 3600)
        try:
            ttl_seconds = int(expires_in)
        except (TypeError, ValueError):
            ttl_seconds = 3600

        self._cached_token = access_token
        self._expires_at_epoch = time.time() + max(ttl_seconds, 0)
        return access_token

    def _ensure_configured(self) -> None:
        missing = [
            name
            for name, value in {
                "SAP_OAUTH_TOKEN_URL": self._settings.sap_oauth_token_url,
                "SAP_COMPANY_ID": self._settings.sap_company_id,
                "SAP_CLIENT_ID": self._settings.sap_client_id,
                "SAP_SAML_ASSERTION": self._settings.sap_saml_assertion,
            }.items()
            if not value
        ]
        if missing:
            raise ConnectorUnavailableError(
                "SAP SAML Bearer authentication is not configured. Missing: " + ", ".join(missing)
            )
