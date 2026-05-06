from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.repositories.models import DemoUserAccessORM, DemoUserORM
from app.schemas.api import DemoUserSummary


class DemoUserRepository:
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

    def seed(self, users: Sequence[DemoUserSummary], access_map: dict[str, list[str]]) -> None:
        with self._session() as session:
            existing = session.scalars(select(DemoUserORM)).all()
            if existing:
                return

            for user in users:
                session.add(
                    DemoUserORM(
                        user_id=user.user_id,
                        display_name=user.display_name,
                        role=user.role,
                        job_title=user.job_title,
                        employee_id=user.employee_id,
                        description=user.description,
                    )
                )

            for user_id, employee_ids in access_map.items():
                for employee_id in employee_ids:
                    session.add(DemoUserAccessORM(user_id=user_id, employee_id=employee_id))

    def list_users(self) -> list[DemoUserSummary]:
        with self._session() as session:
            users = session.scalars(select(DemoUserORM).order_by(DemoUserORM.display_name.asc())).all()
            return [
                DemoUserSummary(
                    user_id=user.user_id,
                    display_name=user.display_name,
                    role=user.role,  # type: ignore[arg-type]
                    job_title=user.job_title,
                    employee_id=user.employee_id,
                    description=user.description,
                )
                for user in users
            ]

    def get_user(self, user_id: str) -> DemoUserSummary | None:
        with self._session() as session:
            user = session.get(DemoUserORM, user_id)
            if not user:
                return None
            return DemoUserSummary(
                user_id=user.user_id,
                display_name=user.display_name,
                role=user.role,  # type: ignore[arg-type]
                job_title=user.job_title,
                employee_id=user.employee_id,
                description=user.description,
            )

    def upsert_user(self, user: DemoUserSummary, allowed_employee_ids: list[str]) -> None:
        with self._session() as session:
            existing = session.get(DemoUserORM, user.user_id)
            if existing:
                existing.display_name = user.display_name
                existing.role = user.role
                existing.job_title = user.job_title
                existing.employee_id = user.employee_id
                existing.description = user.description
            else:
                session.add(DemoUserORM(
                    user_id=user.user_id,
                    display_name=user.display_name,
                    role=user.role,
                    job_title=user.job_title,
                    employee_id=user.employee_id,
                    description=user.description,
                ))
            session.flush()
            session.query(DemoUserAccessORM).filter(DemoUserAccessORM.user_id == user.user_id).delete()
            for emp_id in allowed_employee_ids:
                session.add(DemoUserAccessORM(user_id=user.user_id, employee_id=emp_id))

    def get_allowed_employee_ids(self, user_id: str) -> list[str]:
        with self._session() as session:
            rows = session.scalars(
                select(DemoUserAccessORM.employee_id)
                .where(DemoUserAccessORM.user_id == user_id)
                .order_by(DemoUserAccessORM.employee_id.asc())
            ).all()
            return list(rows)
