from __future__ import annotations

from app.repositories.demo_repository import DemoUserRepository
from app.schemas.api import DemoUserSummary
from app.schemas.domain import Employee, RequestContext
from app.services.errors import DemoUserNotFoundError
from app.services.time import utc_now


class AuthorizationService:
    def __init__(self, demo_user_repository: DemoUserRepository):
        self._demo_user_repository = demo_user_repository

    def build_request_context(self, request_id: str, user_id: str) -> RequestContext:
        user = self._demo_user_repository.get_user(user_id)
        if not user:
            raise DemoUserNotFoundError(f"Demo user '{user_id}' is not configured.")

        return RequestContext(
            request_id=request_id,
            user_id=user.user_id,
            user_display_name=user.display_name,
            user_role=user.role,
            employee_id=user.employee_id,
            allowed_employee_ids=self._demo_user_repository.get_allowed_employee_ids(user.user_id),
            timestamp=utc_now(),
        )

    def list_demo_users(self) -> list[DemoUserSummary]:
        return self._demo_user_repository.list_users()

    def is_authorized(self, context: RequestContext, employee_id: str) -> bool:
        return employee_id in context.allowed_employee_ids

    def filter_authorized_matches(
        self, context: RequestContext, matches: list[Employee]
    ) -> list[Employee]:
        return [match for match in matches if self.is_authorized(context, match.employee_id)]
