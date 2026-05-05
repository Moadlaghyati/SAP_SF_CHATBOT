from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.database import Base
from app.services.time import utc_now


class DemoUserORM(Base):
    __tablename__ = "demo_users"

    user_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    employee_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)


class DemoUserAccessORM(Base):
    __tablename__ = "demo_user_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)


class RequestRecordORM(Base):
    __tablename__ = "request_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    acting_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    acting_user_name: Mapped[str] = mapped_column(String(255), nullable=False)
    acting_user_role: Mapped[str] = mapped_column(String(50), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_employee_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    authorization_outcome: Mapped[str] = mapped_column(String(100), nullable=False, default="pending")
    status: Mapped[str] = mapped_column(String(100), nullable=False, default="processing")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditRecordORM(Base):
    __tablename__ = "audit_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    acting_user: Mapped[str] = mapped_column(String(255), nullable=False)
    user_role: Mapped[str] = mapped_column(String(50), nullable=False)
    original_question: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_called: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_employee: Mapped[str | None] = mapped_column(String(100), nullable=True)
    authorization_outcome: Mapped[str] = mapped_column(String(100), nullable=False)
    final_status: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    data_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
