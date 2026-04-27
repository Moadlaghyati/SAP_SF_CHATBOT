from __future__ import annotations

import json
from contextlib import contextmanager

from sqlalchemy import desc, select
from sqlalchemy.orm import sessionmaker

from app.repositories.models import RequestRecordORM
from app.schemas.api import RequestDetail, RequestListItem
from app.schemas.domain import ToolTrace


class RequestRepository:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    @contextmanager
    def _session(self):
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_request(
        self,
        request_id: str,
        acting_user_id: str,
        acting_user_name: str,
        acting_user_role: str,
        question: str,
    ) -> None:
        with self._session() as session:
            session.add(
                RequestRecordORM(
                    request_id=request_id,
                    acting_user_id=acting_user_id,
                    acting_user_name=acting_user_name,
                    acting_user_role=acting_user_role,
                    question=question,
                )
            )

    def finalize_request(
        self,
        request_id: str,
        *,
        parsed_intent: str | None,
        tool_name: str | None,
        target_employee_id: str | None,
        authorization_outcome: str,
        status: str,
        duration_ms: int,
        answer: str,
        trace: ToolTrace,
    ) -> None:
        with self._session() as session:
            record = session.scalar(select(RequestRecordORM).where(RequestRecordORM.request_id == request_id))
            if not record:
                return
            record.parsed_intent = parsed_intent
            record.tool_name = tool_name
            record.target_employee_id = target_employee_id
            record.authorization_outcome = authorization_outcome
            record.status = status
            record.duration_ms = duration_ms
            record.answer = answer
            record.trace_json = json.dumps(trace.model_dump(mode="json"), ensure_ascii=True)

    def list_requests(self, limit: int = 50) -> list[RequestListItem]:
        with self._session() as session:
            items = session.scalars(
                select(RequestRecordORM).order_by(desc(RequestRecordORM.created_at)).limit(limit)
            ).all()
            return [
                RequestListItem(
                    request_id=item.request_id,
                    created_at=item.created_at,
                    acting_user=item.acting_user_name,
                    user_role=item.acting_user_role,  # type: ignore[arg-type]
                    question=item.question,
                    parsed_intent=item.parsed_intent,
                    tool_name=item.tool_name,
                    target_employee_id=item.target_employee_id,
                    authorization_outcome=item.authorization_outcome,
                    status=item.status,  # type: ignore[arg-type]
                    duration_ms=item.duration_ms,
                )
                for item in items
            ]

    def get_request(self, request_id: str) -> RequestDetail | None:
        with self._session() as session:
            item = session.scalar(select(RequestRecordORM).where(RequestRecordORM.request_id == request_id))
            if not item:
                return None

            trace = ToolTrace.model_validate_json(item.trace_json) if item.trace_json else None
            return RequestDetail(
                request_id=item.request_id,
                created_at=item.created_at,
                acting_user=item.acting_user_name,
                user_role=item.acting_user_role,  # type: ignore[arg-type]
                question=item.question,
                parsed_intent=item.parsed_intent,
                tool_name=item.tool_name,
                target_employee_id=item.target_employee_id,
                authorization_outcome=item.authorization_outcome,
                status=item.status,  # type: ignore[arg-type]
                duration_ms=item.duration_ms,
                answer=item.answer,
                trace=trace,
            )

    def get_trace(self, request_id: str) -> ToolTrace | None:
        detail = self.get_request(request_id)
        return detail.trace if detail else None
