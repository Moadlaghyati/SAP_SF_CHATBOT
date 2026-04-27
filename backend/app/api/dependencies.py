from __future__ import annotations

from fastapi import Header, HTTPException, Request, status

from app.services.container import AppContainer


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_demo_user_id(
    request: Request,
    x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
) -> str:
    container: AppContainer = request.app.state.container
    return x_demo_user_id or container.settings.default_demo_user_id


def not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
