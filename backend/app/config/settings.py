from __future__ import annotations

from datetime import date
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "HR AI Assistant Local MVP"
    app_env: str = "development"
    api_prefix: str = "/api"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    database_url: str = "sqlite:///./hr_ai_assistant.db"
    request_history_limit: int = 50

    default_demo_user_id: str = "demo_manager_meryem"
    demo_reference_date: date = date(2026, 4, 22)

    connector_backend: str = "mock"
    connector_mock_latency_ms: int = 120
    connector_timeout_seconds: float = 15.0

    llm_backend: str = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    llm_timeout_seconds: float = 90.0

    sap_base_url: str | None = None
    sap_company_id: str | None = None
    sap_oauth_token_url: str | None = None
    sap_acting_user_id: str | None = None  # SAP userId of the logged-in user (for "my absences" / "my team" queries)
    sap_hr_admin_user_ids: list[str] = Field(default_factory=list)  # Comma-separated SAP userIds with HR admin access
    sap_auth_mode: str = "basic"
    sap_username: str | None = None
    sap_password: str | None = None
    sap_client_id: str | None = None
    sap_client_secret: str | None = None
    sap_saml_assertion: str | None = None

    @model_validator(mode="after")
    def validate_local_only_backends(self) -> "Settings":
        if self.llm_backend not in {"ollama", "mock"}:
            raise ValueError("LLM_BACKEND must be 'ollama' or 'mock'.")

        if self.connector_backend not in {"mock", "successfactors"}:
            raise ValueError("CONNECTOR_BACKEND must be 'mock' or 'successfactors'.")

        if self.llm_backend == "ollama":
            parsed = urlparse(self.ollama_base_url)
            if parsed.scheme not in {"http", "https"}:
                raise ValueError("OLLAMA_BASE_URL must use http or https.")
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError(
                    "The LLM adapter only permits local Ollama endpoints. "
                    "Use localhost or 127.0.0.1."
                )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
