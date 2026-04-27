from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.llm import ParsedQuestion


def test_parsed_question_accepts_supported_payload() -> None:
    payload = ParsedQuestion(
        intent="absence_count",
        employee_reference="Sara Bennani",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        absence_type=None,
        needs_clarification=False,
    )

    assert payload.intent == "absence_count"
    assert payload.start_date == date(2026, 1, 1)


def test_parsed_question_rejects_missing_dates_without_clarification() -> None:
    with pytest.raises(ValidationError):
        ParsedQuestion(
            intent="absence_count",
            employee_reference="Sara Bennani",
            start_date=None,
            end_date=None,
            needs_clarification=False,
        )


def test_parsed_question_accepts_general_chat_without_employee_or_dates() -> None:
    payload = ParsedQuestion(
        intent="general_chat",
        employee_reference=None,
        start_date=None,
        end_date=None,
        needs_clarification=False,
    )

    assert payload.intent == "general_chat"
