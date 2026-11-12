from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db, get_services
from app.container import Services
from app.core.auth import issue_token, verify_password
from app.core.errors import AppError
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse, UserOut
from app.storage.models import Institution, User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest, db: Session = Depends(get_db), services: Services = Depends(get_services)
) -> LoginResponse:
    user = db.scalar(select(User).where(User.username == body.username))
    if not verify_password(body.password, user.password_hash if user else None) or user is None:
        raise AppError(401, "unauthorized", "아이디 또는 비밀번호가 올바르지 않습니다.")
    s = services.settings
    token = issue_token(
        s.auth_secret.get_secret_value(), user.id, user.institution_id, user.role, s.auth_token_ttl_seconds
    )
    return LoginResponse(
        access_token=token,
        expires_in=s.auth_token_ttl_seconds,
        user=UserOut(id=user.id, username=user.username, institution_id=user.institution_id, role=user.role),
    )


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(current_user), db: Session = Depends(get_db)) -> MeResponse:
    inst = db.get(Institution, user.institution_id)
    return MeResponse(
        id=user.id,
        username=user.username,
        institution_id=user.institution_id,
        institution_name=inst.name if inst else user.institution_id,
        role=user.role,
    )
