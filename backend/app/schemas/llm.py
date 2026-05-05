from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.schemas.domain import IntentType


class ParsedQuestion(BaseModel):
    intent: IntentType
    employee_reference: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    absence_type: str | None = None
    needs_clarification: bool = False
    clarification_reason: str | None = None

    @model_validator(mode="after")
    def validate_fields(self) -> "ParsedQuestion":
        if self.intent in {"unsupported", "general_chat"}:
            return self

        if self.needs_clarification:
            return self

        if not self.employee_reference:
            raise ValueError("employee_reference is required for supported intents.")

        if self.start_date is None or self.end_date is None:
            raise ValueError("start_date and end_date are required when clarification is not needed.")

        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date.")

        return self


class AnswerGenerationPayload(BaseModel):
    request_status: str
    intent: str | None = None
    employee_name: str | None = None
    user_message: str | None = None
    result: dict = Field(default_factory=dict)
    clarification_options: list[str] = Field(default_factory=list)
    supported_capabilities: list[str] = Field(default_factory=list)
    error_message: str | None = None


class AbsenceExtractionResult(BaseModel):
    scope: str = "unknown"
    employee_name: str | None = None
    employee_name_b: str | None = None
    user_id: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    needs_clarification: bool = False
    clarification_message: str | None = None
