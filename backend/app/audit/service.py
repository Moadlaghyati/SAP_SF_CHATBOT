from __future__ import annotations

import logging
import re

from app.repositories.audit_repository import AuditRepository
from app.schemas.domain import AuditRecord, RequestStatus
from app.services.time import utc_now

LOGGER = logging.getLogger(__name__)


class RedactionService:
    _patterns = [
        (re.compile(r"(password|secret|token)\s*[:=]\s*([^\s,;]+)", re.IGNORECASE), r"\1=[REDACTED]"),
        (re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE), "Bearer [REDACTED]"),
    ]

    def redact_text(self, value: str) -> str:
        redacted = value
        for pattern, replacement in self._patterns:
            redacted = pattern.sub(replacement, redacted)
        return redacted


class AuditService:
    def __init__(self, repository: AuditRepository, redaction_service: RedactionService):
        self._repository = repository
        self._redaction_service = redaction_service

    def record(
        self,
        *,
        request_id: str,
        acting_user: str,
        user_role: str,
        original_question: str,
        parsed_intent: str | None,
        tool_called: str | None,
        target_employee: str | None,
        authorization_outcome: str,
        final_status: RequestStatus,
        duration_ms: int,
        data_source: str | None,
    ) -> None:
        LOGGER.info(
            "audit request_id=%s user=%s role=%s intent=%s status=%s question=%s",
            request_id,
            acting_user,
            user_role,
            parsed_intent,
            final_status,
            self._redaction_service.redact_text(original_question),
        )
        self._repository.create(
            AuditRecord(
                request_id=request_id,
                timestamp=utc_now(),
                acting_user=acting_user,
                user_role=user_role,  # type: ignore[arg-type]
                original_question=original_question,
                parsed_intent=parsed_intent,
                tool_called=tool_called,
                target_employee=target_employee,
                authorization_outcome=authorization_outcome,
                final_status=final_status,
                duration_ms=duration_ms,
                data_source=data_source,
            )
        )
