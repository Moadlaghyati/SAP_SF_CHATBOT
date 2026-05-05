from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.agents.sap.department_overlap_agent import DepartmentOverlapAgent
from app.agents.sap.sap_absence_agent import SapAbsenceAgent
from app.agents.sap.sap_auth_service import SapAuthService
from app.agents.sap.sap_success_factors_client import SapSuccessFactorsClient
from app.audit.service import AuditService, RedactionService
from app.auth.service import AuthorizationService
from app.config.settings import Settings
from app.connectors.base import SuccessFactorsConnector
from app.connectors.mock_data import DEMO_ACCESS_MAP, DEMO_USERS, MOCK_EMPLOYEES
from app.connectors.mock_sap_client import MockSapClient
from app.connectors.mock_successfactors import MockSuccessFactorsConnector
from app.connectors.real_successfactors import RealSuccessFactorsConnector
from app.llm.base import LocalLLMClient
from app.llm.mock import MockLocalLLMClient
from app.llm.ollama import OllamaClient
from app.orchestrator.service import ChatOrchestrator
from app.repositories.audit_repository import AuditRepository
from app.repositories.database import Base, create_engine_and_session_factory
from app.repositories.demo_repository import DemoUserRepository
from app.repositories.request_repository import RequestRepository
from app.schemas.api import HealthComponent, HealthResponse
from app.schemas.domain import LocalModelSummary
from app.services.time import utc_now
from app.tools.service import ToolService

LOGGER = logging.getLogger(__name__)


class AppContainer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine, self.session_factory = create_engine_and_session_factory(settings.database_url)

        self.demo_user_repository = DemoUserRepository(self.session_factory)
        self.request_repository = RequestRepository(self.session_factory)
        self.audit_repository = AuditRepository(self.session_factory)

        self.connector: SuccessFactorsConnector = self._build_connector()
        self.llm_client: LocalLLMClient = self._build_llm_client()
        self.sap_auth_service: SapAuthService | None = None
        self.sap_success_factors_client: SapSuccessFactorsClient | None = None
        self.sap_absence_agent: SapAbsenceAgent | None = None
        self.dept_overlap_agent: DepartmentOverlapAgent | None = None
        # Populated at startup: maps mock employee_id -> real SAP userId
        self.sap_employee_id_map: dict[str, str] = {}
        self._build_sap_agents()
        self.authorization_service = AuthorizationService(self.demo_user_repository)
        self.audit_service = AuditService(self.audit_repository, RedactionService())
        self.tool_service = ToolService(self.connector, self.request_repository)
        self.orchestrator = ChatOrchestrator(
            settings=settings,
            authorization_service=self.authorization_service,
            tool_service=self.tool_service,
            request_repository=self.request_repository,
            audit_service=self.audit_service,
            llm_client=self.llm_client,
            sap_absence_agent=self.sap_absence_agent,
            dept_overlap_agent=self.dept_overlap_agent,
            sap_employee_id_map=self.sap_employee_id_map,
        )

    def _build_connector(self) -> SuccessFactorsConnector:
        if self.settings.connector_backend == "successfactors":
            return RealSuccessFactorsConnector(self.settings)
        return MockSuccessFactorsConnector(latency_ms=self.settings.connector_mock_latency_ms)

    def _build_llm_client(self) -> LocalLLMClient:
        if self.settings.llm_backend == "mock":
            return MockLocalLLMClient()
        return OllamaClient(self.settings)

    def _build_sap_agents(self) -> None:
        from datetime import date as _date
        provider = lambda: _date.today()

        if self.settings.connector_backend == "successfactors":
            self.sap_auth_service = SapAuthService(self.settings)
            self.sap_success_factors_client = SapSuccessFactorsClient(
                settings=self.settings,
                auth_service=self.sap_auth_service,
            )
            sap_client = self.sap_success_factors_client
        else:
            sap_client = MockSapClient()

        self.sap_absence_agent = SapAbsenceAgent(
            client=sap_client,
            current_date_provider=provider,
            llm_client=self.llm_client,
        )
        self.dept_overlap_agent = DepartmentOverlapAgent(
            client=sap_client,
            current_date_provider=provider,
        )

    async def startup(self) -> None:
        Base.metadata.create_all(bind=self.engine)
        self.demo_user_repository.seed(DEMO_USERS, DEMO_ACCESS_MAP)
        if self.settings.connector_backend == "successfactors" and self.sap_success_factors_client:
            await self._resolve_sap_employee_ids()
        LOGGER.info("Application container started with connector=%s llm=%s", self.connector.backend_name, self.llm_client.backend_name)

    async def _resolve_sap_employee_ids(self) -> None:
        """Resolve all demo employee names to their real SAP userIds at startup."""
        for emp in MOCK_EMPLOYEES:
            try:
                # Hardcoded override takes priority — no API call needed
                if emp.sap_user_id:
                    self.sap_employee_id_map[emp.employee_id] = emp.sap_user_id
                    LOGGER.info("[SAP] Resolved employee %s (%s) -> SAP userId %s (hardcoded)", emp.display_name, emp.employee_id, emp.sap_user_id)
                    continue

                real_id = await self.sap_success_factors_client.resolve_user_id_by_name(emp.display_name)  # type: ignore[union-attr]
                if not real_id:
                    LOGGER.info("[SAP] Name lookup failed for %s (%s), trying personIdExternal fallback", emp.display_name, emp.employee_id)
                    real_id = await self.sap_success_factors_client.resolve_user_id_by_person_id(person_id=emp.employee_id)  # type: ignore[union-attr]
                if not real_id:
                    LOGGER.info("[SAP] personIdExternal fallback failed for %s (%s), checking if mock ID is valid SAP userId", emp.display_name, emp.employee_id)
                    if await self.sap_success_factors_client.verify_user_id_exists(emp.employee_id):  # type: ignore[union-attr]
                        real_id = emp.employee_id
                if real_id:
                    self.sap_employee_id_map[emp.employee_id] = real_id
                    LOGGER.info("[SAP] Resolved employee %s (%s) -> SAP userId %s", emp.display_name, emp.employee_id, real_id)
                else:
                    LOGGER.warning("[SAP] Could not resolve SAP userId for %s (%s), using mock ID as fallback", emp.display_name, emp.employee_id)
            except Exception as exc:
                LOGGER.warning("[SAP] Error resolving SAP userId for %s: %s", emp.display_name, exc)

    async def shutdown(self) -> None:
        close_connector = getattr(self.connector, "close", None)
        if callable(close_connector):
            await close_connector()
        if self.sap_success_factors_client is not None:
            await self.sap_success_factors_client.close()
        if self.sap_auth_service is not None:
            await self.sap_auth_service.close()
        close_llm = getattr(self.llm_client, "close", None)
        if callable(close_llm):
            await close_llm()

    async def health_check(self) -> HealthResponse:
        components = [
            self._database_health_component(self.engine, self.session_factory),
            await self._connector_health_component(),
            await self._llm_health_component(),
        ]
        overall_ok = all(component.ok for component in components)
        return HealthResponse(
            status="ok" if overall_ok else "degraded",
            timestamp=utc_now(),
            connector_backend=self.connector.backend_name,
            llm_backend=self.llm_client.backend_name,
            llm_model=self.settings.ollama_model if self.settings.llm_backend == "ollama" else "mock",
            components=components,
        )

    async def list_local_models(self) -> list[LocalModelSummary]:
        return await self.llm_client.list_available_models()

    def active_llm_model(self) -> str | None:
        if self.settings.llm_backend == "ollama":
            return self.settings.ollama_model
        return "mock"

    async def switch_local_model(self, model_name: str) -> str:
        if self.settings.llm_backend != "ollama":
            raise ValueError("Local model switching is available only when LLM_BACKEND=ollama.")

        installed = {item.name for item in await self.llm_client.list_available_models()}
        if model_name not in installed:
            raise ValueError(
                f"Model '{model_name}' is not installed locally. Run `ollama pull {model_name}` first."
            )

        self.settings.ollama_model = model_name
        return model_name

    def _database_health_component(
        self, engine: Engine, session_factory: sessionmaker
    ) -> HealthComponent:
        _ = engine
        try:
            with session_factory() as session:
                session.execute(text("SELECT 1"))
            return HealthComponent(name="database", ok=True, details="SQLite database is reachable.")
        except Exception as exc:
            return HealthComponent(name="database", ok=False, details=f"Database unavailable: {exc}")

    async def _connector_health_component(self) -> HealthComponent:
        ok, details = await self.connector.health_check()
        return HealthComponent(name="connector", ok=ok, details=details)

    async def _llm_health_component(self) -> HealthComponent:
        ok, details = await self.llm_client.health_check()
        return HealthComponent(name="local_llm", ok=ok, details=details)
