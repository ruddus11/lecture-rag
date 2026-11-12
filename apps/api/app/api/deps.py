"""라우트 공통 의존성: db 세션, 현재 사용자, 관리자 확인, 서비스 묶음."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.container import Services
from app.core.auth import decode_token
from app.core.errors import AppError
from app.core.logging import user_id_var
from app.storage.models import User

_bearer = HTTPBearer(auto_error=False)


def get_services(request: Request) -> Services:
    return request.app.state.services  # type: ignore[no-any-return]


def get_db(services: Services = Depends(get_services)) -> Iterator[Session]:
    with services.db.session() as s:
        yield s


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    services: Services = Depends(get_services),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise AppError(401, "unauthorized", "로그인이 필요합니다.")
    claims = decode_token(services.settings.auth_secret.get_secret_value(), creds.credentials)
    user = db.get(User, claims.sub)
    if user is None:
        raise AppError(401, "unauthorized", "인증 정보가 올바르지 않습니다.")
    user_id_var.set(user.id)
    return user


async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise AppError(403, "forbidden_role", "관리자만 수행할 수 있습니다.")
    return user
