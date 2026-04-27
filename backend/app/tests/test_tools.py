from __future__ import annotations

from datetime import date

import pytest

from app.services.container import AppContainer


@pytest.mark.asyncio
async def test_resolve_employee_and_authorized_filter(container: AppContainer) -> None:
    manager_context = container.authorization_service.build_request_context(
        "req_manager", "demo_manager_meryem"
    )
    matches = await container.tool_service.resolve_employee("Yasmine", manager_context)
    authorized_matches = container.authorization_service.filter_authorized_matches(manager_context, matches)

    assert len(matches) == 2
    assert len(authorized_matches) == 1
    assert authorized_matches[0].display_name == "Yasmine Alami"


@pytest.mark.asyncio
async def test_count_absences_summary_for_sara_q1(container: AppContainer) -> None:
    summary = await container.tool_service.count_absences(
        employee_id="E1001",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )

    assert summary.absence_count == 4
    assert summary.absence_days == 6.5
    assert {item.type for item in summary.by_type} == {"Annual Leave", "Sick Leave"}
