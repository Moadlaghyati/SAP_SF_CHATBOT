from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import pytest

from app.agents.sap.absence_extraction import extract_absence_retrieval_params
from app.agents.sap.absence_formatter import normalize_employee_absences
from app.agents.sap.absence_intent import detect_absence_intent
from app.agents.sap.sap_absence_agent import SapAbsenceAgent
from app.agents.sap.sap_auth_service import SapAuthService
from app.agents.sap.sap_success_factors_client import SapSuccessFactorsClient
from app.config.settings import Settings


def sap_settings(**overrides) -> Settings:
    values = {
        "llm_backend": "mock",
        "connector_backend": "mock",
        "sap_base_url": "https://api012.successfactors.eu/odata/v2",
        "sap_company_id": "iconunternD",
        "sap_oauth_token_url": "https://api012.successfactors.eu/oauth/token",
        "sap_client_id": "client-from-env",
        "sap_saml_assertion": "assertion-from-env",
    }
    values.update(overrides)
    return Settings(**values)


def test_absence_intent_detection_triggers_for_absence_terms() -> None:
    result = detect_absence_intent("Show me absences for user 90000638 in 2026")

    assert result.should_handle is True
    assert result.confidence >= 0.9


def test_absence_intent_detection_triggers_for_absent_word() -> None:
    result = detect_absence_intent("Who was absent in March 2026?")

    assert result.should_handle is True


def test_absence_intent_detection_ignores_unrelated_questions() -> None:
    result = detect_absence_intent("What is the company policy?")

    assert result.should_handle is False


def test_extracts_user_id_and_year_range() -> None:
    params = extract_absence_retrieval_params(
        "Show me absences for user 90000638 in 2026",
        current_date=date(2026, 4, 27),
    )

    assert params.user_id == "90000638"
    assert params.start_date == "2026-01-01"
    assert params.end_date == "2026-12-31"
    assert params.year == 2026


def test_extracts_employee_name_and_defaults_to_current_year() -> None:
    params = extract_absence_retrieval_params(
        "Get vacation days for John Smith this year",
        current_date=date(2026, 4, 27),
    )

    assert params.employee_name == "John Smith"
    assert params.start_date == "2026-01-01"
    assert params.end_date == "2026-12-31"
    assert params.missing_required_fields == []


def test_extracts_workforce_month_year_without_employee_identifier() -> None:
    params = extract_absence_retrieval_params(
        "Who is absent in March 2026?",
        current_date=date(2026, 4, 27),
    )

    assert params.scope == "workforce"
    assert params.start_date == "2026-03-01"
    assert params.end_date == "2026-03-31"
    assert params.month == 3
    assert params.missing_required_fields == []


def test_extracts_workforce_french_month_year() -> None:
    params = extract_absence_retrieval_params(
        "Who was absent in avril 2026?",
        current_date=date(2026, 4, 27),
    )

    assert params.scope == "workforce"
    assert params.start_date == "2026-04-01"
    assert params.end_date == "2026-04-30"
    assert params.month == 4
    assert params.missing_required_fields == []


def test_extracts_company_wide_absence_request_as_workforce_scope() -> None:
    params = extract_absence_retrieval_params(
        "I want to see all absences in this company in 2026",
        current_date=date(2026, 4, 27),
    )

    assert params.scope == "workforce"
    assert params.start_date == "2026-01-01"
    assert params.end_date == "2026-12-31"
    assert params.missing_required_fields == []


def test_extracts_workforce_single_day_without_employee_identifier() -> None:
    params = extract_absence_retrieval_params(
        "Are there any employees that will have vacations this day 2026-05-07?",
        current_date=date(2026, 4, 27),
    )

    assert params.scope == "workforce"
    assert params.start_date == "2026-05-07"
    assert params.end_date == "2026-05-07"
    assert params.missing_required_fields == []


def test_builds_url_encoded_employee_time_query() -> None:
    auth_service = object()
    client = SapSuccessFactorsClient(settings=sap_settings(), auth_service=auth_service)

    url = client.build_employee_absences_url(
        user_id="90000638",
        start_date="2026-01-01",
        end_date="2026-12-31",
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.path.endswith("/odata/v2/EmployeeTime")
    assert query["$format"] == ["json"]
    decoded_filter = unquote(query["$filter"][0])
    assert decoded_filter == (
        "userId eq '90000638' and startDate ge datetime'2026-01-01T00:00:00' "
        "and endDate le datetime'2026-12-31T23:59:59'"
    )


def test_builds_url_encoded_workforce_absence_query() -> None:
    auth_service = object()
    client = SapSuccessFactorsClient(settings=sap_settings(), auth_service=auth_service)

    url = client.build_absences_url(start_date="2026-05-07", end_date="2026-05-07")

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.path.endswith("/odata/v2/EmployeeTime")
    decoded_filter = unquote(query["$filter"][0])
    assert decoded_filter == (
        "startDate le datetime'2026-05-07T23:59:59' "
        "and endDate ge datetime'2026-05-07T00:00:00'"
    )


@pytest.mark.asyncio
async def test_client_follows_successfactors_pagination() -> None:
    class FakeAuthService:
        async def get_access_token(self) -> str:
            return "token"

    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "d": {
                        "results": [{"userId": "1", "startDate": "2026-01-01", "endDate": "2026-01-01"}],
                        "__next": "https://api012.successfactors.eu/odata/v2/EmployeeTime?$skiptoken=abc",
                    }
                },
            )
        return httpx.Response(
            200,
            json={"d": {"results": [{"userId": "2", "startDate": "2026-01-02", "endDate": "2026-01-02"}]}},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = SapSuccessFactorsClient(
            settings=sap_settings(),
            auth_service=FakeAuthService(),
            client=http_client,
        )
        records = await client.get_absences(start_date="2026-01-01", end_date="2026-01-31")

    assert [record.user_id for record in records] == ["1", "2"]
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_auth_service_caches_access_token() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = request.content.decode()
        assert "client-from-env" in body
        assert "assertion-from-env" in body
        return httpx.Response(200, json={"access_token": f"token-{calls}", "expires_in": 3600})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        service = SapAuthService(sap_settings(), client=http_client)
        first = await service.get_access_token()
        second = await service.get_access_token()

    assert first == "token-1"
    assert second == "token-1"
    assert calls == 1


def test_normalizes_employee_time_results_defensively() -> None:
    records = normalize_employee_absences(
        {
            "d": {
                "results": [
                    {
                        "userId": "90000638",
                        "startDate": "2026-02-10T00:00:00",
                        "endDate": "2026-02-14T00:00:00",
                        "timeType": "Vacation",
                        "approvalStatus": "APPROVED",
                        "quantityInDays": "5",
                        "externalCode": "A1",
                    },
                    {"userId": "90000638"},
                ]
            }
        }
    )

    assert len(records) == 2
    assert records[0].absence_type == "Vacation"
    assert records[0].quantity_in_days == 5.0
    assert records[1].start_date == ""


def test_normalizes_successfactors_epoch_dates() -> None:
    records = normalize_employee_absences(
        {
            "d": {
                "results": [
                    {
                        "userId": "90000638",
                        "startDate": "/Date(1768176000000)/",
                        "endDate": "/Date(1768262400000)/",
                    }
                ]
            }
        }
    )

    assert records[0].start_date == "2026-01-12"
    assert records[0].end_date == "2026-01-13"


@pytest.mark.asyncio
async def test_agent_handles_workforce_request_without_employee_identifier() -> None:
    class FakeClient:
        async def get_absences(self, *, start_date: str, end_date: str):
            assert start_date == "2026-03-01"
            assert end_date == "2026-03-31"
            return []

    agent = SapAbsenceAgent(client=FakeClient(), current_date_provider=lambda: date(2026, 4, 27))

    result = await agent.handle("Who is absent in March 2026?")

    assert result.handled is True
    assert result.status == "success"


@pytest.mark.asyncio
async def test_agent_returns_not_applicable_for_unrelated_question() -> None:
    agent = SapAbsenceAgent(client=object(), current_date_provider=lambda: date(2026, 4, 27))

    result = await agent.handle("What is the company policy?")

    assert result.handled is False
    assert result.status == "not_applicable"
