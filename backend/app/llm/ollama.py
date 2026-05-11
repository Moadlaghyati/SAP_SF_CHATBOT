from __future__ import annotations

from datetime import date

import httpx

from app.config.settings import Settings
from app.llm.base import LocalLLMClient
from app.llm.prompts import build_absence_extraction_prompt, build_answer_prompt, build_extraction_prompt, build_intent_analysis_prompt, build_structured_answer_prompt
from app.schemas.domain import LocalModelSummary
from app.schemas.llm import AbsenceExtractionResult, AnswerGenerationPayload, ParsedQuestion, StructuredIntent
from app.services.errors import LocalLLMUnavailableError, StructuredOutputError


class OllamaClient(LocalLLMClient):
    backend_name = "ollama"

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_base_url.rstrip("/"),
            timeout=settings.llm_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def extract_question(self, question: str, current_date: date) -> ParsedQuestion:
        prompt = build_extraction_prompt(question, current_date)
        try:
            response = await self._client.post(
                "/api/generate",
                json={
                    "model": self._settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0},
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self._map_http_error(exc) from exc

        body = response.json()
        raw_response = body.get("response", "").strip()
        try:
            return ParsedQuestion.model_validate_json(raw_response)
        except ValueError as exc:
            raise StructuredOutputError("The local model returned malformed structured output.") from exc

    async def extract_absence_params(self, question: str, current_date: date) -> AbsenceExtractionResult:
        prompt = build_absence_extraction_prompt(question, current_date)
        try:
            response = await self._client.post(
                "/api/generate",
                json={
                    "model": self._settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0},
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self._map_http_error(exc) from exc

        raw = response.json().get("response", "").strip()
        try:
            return AbsenceExtractionResult.model_validate_json(raw)
        except ValueError:
            return AbsenceExtractionResult(needs_clarification=True, clarification_message="I could not understand that request. Please try rephrasing.")

    async def generate_answer(self, payload: AnswerGenerationPayload) -> str:
        prompt = build_answer_prompt(payload)
        try:
            response = await self._client.post(
                "/api/generate",
                json={
                    "model": self._settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self._map_http_error(exc) from exc

        answer = response.json().get("response", "").strip()
        if not answer:
            raise StructuredOutputError("The local model returned an empty final answer.")
        return answer

    async def analyze_intent(self, question: str, current_date: date, acting_user_display_name: str | None = None) -> StructuredIntent:
        from app.schemas.llm import StructuredIntent
        prompt = build_intent_analysis_prompt(question, current_date, acting_user_display_name)
        try:
            response = await self._client.post(
                "/api/generate",
                json={
                    "model": self._settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.2, "num_ctx": 2048, "num_predict": 300},
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self._map_http_error(exc) from exc
        raw = response.json().get("response", "").strip()
        try:
            return StructuredIntent.model_validate_json(raw)
        except Exception:
            return StructuredIntent(intent="unknown", clarification_needed=False)

    async def generate_structured_answer(self, user_message: str, intent_json: dict, sap_result: dict) -> str:
        from app.llm.prompts import build_structured_answer_prompt
        prompt = build_structured_answer_prompt(user_message, intent_json, sap_result)
        try:
            response = await self._client.post(
                "/api/generate",
                json={
                    "model": self._settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_ctx": 2048, "num_predict": 150},
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self._map_http_error(exc) from exc
        answer = response.json().get("response", "").strip()
        return answer or "No matching absence information was found."

    async def health_check(self) -> tuple[bool, str]:
        try:
            models = await self.list_available_models()
        except LocalLLMUnavailableError as exc:
            return False, str(exc)
        model_names = {item.name for item in models}
        if self._settings.ollama_model not in model_names:
            return (
                False,
                f"Ollama is reachable but model '{self._settings.ollama_model}' is not installed locally.",
            )
        return True, f"Ollama is reachable at {self._settings.ollama_base_url} with model '{self._settings.ollama_model}'."

    async def list_available_models(self) -> list[LocalModelSummary]:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LocalLLMUnavailableError(
                f"Ollama unavailable: {exc}"
            ) from exc

        items = response.json().get("models", [])
        summaries: list[LocalModelSummary] = []
        for item in items:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            details = item.get("details", {}) if isinstance(item.get("details"), dict) else {}
            summaries.append(
                LocalModelSummary(
                    name=item["name"],
                    modified_at=item.get("modified_at"),
                    size=item.get("size"),
                    family=details.get("family"),
                    parameter_size=details.get("parameter_size"),
                    quantization_level=details.get("quantization_level"),
                )
            )
        return summaries

    def _map_http_error(self, exc: httpx.HTTPError) -> LocalLLMUnavailableError:
        if isinstance(exc, httpx.ConnectError):
            return LocalLLMUnavailableError(
                f"Ollama could not be reached at {self._settings.ollama_base_url}. "
                "Start the Ollama app and restart the backend in ollama mode."
            )

        if isinstance(exc, httpx.ReadTimeout):
            return LocalLLMUnavailableError(
                f"Ollama did not finish within {self._settings.llm_timeout_seconds:.0f} seconds. "
                "Try again, use a smaller model, or increase LLM_TIMEOUT_SECONDS."
            )

        if isinstance(exc, httpx.HTTPStatusError):
            body = exc.response.text.strip()
            if exc.response.status_code == 404 or "model" in body.lower() and "not found" in body.lower():
                return LocalLLMUnavailableError(
                    f"Ollama is reachable but model '{self._settings.ollama_model}' is not installed locally. "
                    f"Run `ollama pull {self._settings.ollama_model}` or change OLLAMA_MODEL."
                )

        return LocalLLMUnavailableError(
            "Ollama is unavailable. Start the local runtime and restart the backend in ollama mode."
        )
