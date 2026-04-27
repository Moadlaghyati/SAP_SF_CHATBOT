from __future__ import annotations

from app.services.container import AppContainer


def test_demo_authorization_scopes(container: AppContainer) -> None:
    sara_context = container.authorization_service.build_request_context("req_sara", "demo_employee_sara")
    manager_context = container.authorization_service.build_request_context(
        "req_manager", "demo_manager_meryem"
    )
    hr_admin_context = container.authorization_service.build_request_context(
        "req_hr", "demo_hr_admin_nadia"
    )

    assert sara_context.allowed_employee_ids == ["E1001"]
    assert "E1002" in manager_context.allowed_employee_ids
    assert "E1006" in hr_admin_context.allowed_employee_ids
