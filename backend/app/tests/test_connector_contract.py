from __future__ import annotations

from datetime import date

import pytest

from app.connectors.base import SuccessFactorsConnector
from app.connectors.mock_successfactors import MockSuccessFactorsConnector
from app.connectors.real_successfactors import RealSuccessFactorsConnector
from app.config.settings import Settings
from app.schemas.domain import Employee
from app.services.errors import ConnectorUnavailableError


@pytest.mark.asyncio
async def test_connector_contracts_are_consistent() -> None:
    mock_connector = MockSuccessFactorsConnector(latency_ms=0)
    real_connector = RealSuccessFactorsConnector(
        Settings(
            database_url="sqlite:///./unused.db",
            llm_backend="mock",
            connector_backend="successfactors",
        )
    )

    assert isinstance(mock_connector, SuccessFactorsConnector)
    assert isinstance(real_connector, SuccessFactorsConnector)

    employees = await mock_connector.search_employees("Sara Bennani")
    assert employees
    assert isinstance(employees[0], Employee)

    with pytest.raises(ConnectorUnavailableError):
        await real_connector.list_absences("E1001", date(2026, 1, 1), date(2026, 3, 31))

    await real_connector.close()
