from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.schemas.domain import LocalModelSummary
from app.schemas.llm import AnswerGenerationPayload, ParsedQuestion


class LocalLLMClient(ABC):
    backend_name: str

    @abstractmethod
    async def extract_question(self, question: str, current_date: date) -> ParsedQuestion:
        raise NotImplementedError

    @abstractmethod
    async def generate_answer(self, payload: AnswerGenerationPayload) -> str:
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> tuple[bool, str]:
        raise NotImplementedError

    @abstractmethod
    async def list_available_models(self) -> list[LocalModelSummary]:
        raise NotImplementedError
