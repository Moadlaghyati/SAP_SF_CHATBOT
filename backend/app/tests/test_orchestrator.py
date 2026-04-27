from __future__ import annotations

import pytest

from app.services.container import AppContainer


@pytest.mark.asyncio
async def test_unsupported_question_fallback(container: AppContainer) -> None:
    response = await container.orchestrator.handle_message(
        "What is Sara Bennani's payroll amount?",
        "demo_manager_meryem",
    )

    assert response.status == "unsupported"
    assert "absence counts" in response.answer
    assert response.trace.external_ai_calls == "none"


@pytest.mark.asyncio
async def test_general_chat_greeting_returns_success(container: AppContainer) -> None:
    response = await container.orchestrator.handle_message(
        "hello",
        "demo_manager_meryem",
    )

    assert response.status == "success"
    assert response.trace.detected_intent == "general_chat"
    assert response.trace.tool_name is None
    assert "hello" in response.answer.lower() or "local hr assistant" in response.answer.lower()


@pytest.mark.asyncio
async def test_general_chat_math_question_returns_success(container: AppContainer) -> None:
    response = await container.orchestrator.handle_message(
        "how much is 3+3",
        "demo_manager_meryem",
    )

    assert response.status == "success"
    assert response.trace.detected_intent == "general_chat"
    assert response.trace.tool_name is None
    assert "6" in response.answer


@pytest.mark.asyncio
async def test_ambiguous_employee_handling(container: AppContainer) -> None:
    response = await container.orchestrator.handle_message(
        "Show the absence breakdown by type for Yasmine in February 2026.",
        "demo_hr_admin_nadia",
    )

    assert response.status == "clarification_required"
    assert response.trace.authorization_outcome == "ambiguous"
    assert "multiple matching employees" in response.answer.lower()


@pytest.mark.asyncio
async def test_forbidden_access_handling(container: AppContainer) -> None:
    response = await container.orchestrator.handle_message(
        "How many absences did Karim Ouali have in March 2026?",
        "demo_manager_meryem",
    )

    assert response.status == "forbidden"
    assert response.trace.authorization_outcome == "forbidden"
    assert "do not have permission" in response.answer.lower()
