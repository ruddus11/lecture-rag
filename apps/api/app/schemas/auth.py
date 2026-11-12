from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.config import PASSWORD_MAX, PASSWORD_MIN, USERNAME_MAX, USERNAME_MIN


class LoginRequest(BaseModel):
    username: str = Field(min_length=USERNAME_MIN, max_length=USERNAME_MAX)
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)


class UserOut(BaseModel):
    id: str
    username: str
    institution_id: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class MeResponse(UserOut):
    institution_name: str
