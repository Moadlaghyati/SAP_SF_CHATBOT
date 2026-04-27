from __future__ import annotations

from fastapi.testclient import TestClient


def test_chat_endpoint_happy_path(client: TestClient) -> None:
    response = client.post(
        "/api/chat",
        headers={"X-Demo-User-Id": "demo_manager_meryem"},
        json={"message": "How many absences did Sara Bennani have between 2026-01-01 and 2026-03-31?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["trace"]["tool_name"] == "count_absences"
    assert payload["trace"]["external_ai_calls"] == "none"


def test_health_endpoint_exposes_configured_llm_model(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm_backend"] == "mock"
    assert payload["llm_model"] == "mock"


def test_local_models_endpoint_returns_mock_model(client: TestClient) -> None:
    response = client.get("/api/demo/local-models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["backend"] == "mock"
    assert payload["active_model"] == "mock"
    assert payload["items"][0]["name"] == "mock"


def test_switch_local_model_rejects_non_ollama_backend(client: TestClient) -> None:
    response = client.post("/api/demo/switch-model", json={"model": "qwen2.5:7b"})

    assert response.status_code == 400
    assert "LLM_BACKEND=ollama" in response.text
