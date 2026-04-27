from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import desc, select
from sqlalchemy.orm import sessionmaker

from app.repositories.models import AuditRecordORM
from app.schemas.domain import AuditRecord


class AuditRepository:
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

    def create(self, record: AuditRecord) -> None:
        with self._session() as session:
            session.add(
                AuditRecordORM(
                    request_id=record.request_id,
                    timestamp=record.timestamp,
                    acting_user=record.acting_user,
                    user_role=record.user_role,
                    original_question=record.original_question,
                    parsed_intent=record.parsed_intent,
                    tool_called=record.tool_called,
                    target_employee=record.target_employee,
                    authorization_outcome=record.authorization_outcome,
                    final_status=record.final_status,
                    duration_ms=record.duration_ms,
                    data_source=record.data_source,
                )
            )

    def list_records(self, limit: int = 100) -> list[AuditRecord]:
        with self._session() as session:
            rows = session.scalars(
                select(AuditRecordORM).order_by(desc(AuditRecordORM.timestamp)).limit(limit)
            ).all()
            return [
                AuditRecord(
                    request_id=row.request_id,
                    timestamp=row.timestamp,
                    acting_user=row.acting_user,
                    user_role=row.user_role,  # type: ignore[arg-type]
                    original_question=row.original_question,
                    parsed_intent=row.parsed_intent,
                    tool_called=row.tool_called,
                    target_employee=row.target_employee,
                    authorization_outcome=row.authorization_outcome,
                    final_status=row.final_status,  # type: ignore[arg-type]
                    duration_ms=row.duration_ms,
                    data_source=row.data_source,
                )
                for row in rows
            ]
