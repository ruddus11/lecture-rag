"""비밀번호 해시(bcrypt)와 JWT(HS256) 발급·검증."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.errors import AppError

ALGORITHM = "HS256"
# 존재하지 않는 사용자에도 같은 시간을 쓰도록 비교용 더미 해시를 둔다.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt(rounds=12))


def hash_password(password: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=rounds)).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        bcrypt.checkpw(password.encode(), _DUMMY_HASH)
        return False
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


@dataclass(frozen=True)
class TokenClaims:
    sub: str
    inst: str
    role: str


def issue_token(secret: str, user_id: str, institution_id: str, role: str, ttl_seconds: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "inst": institution_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(secret: str, token: str) -> TokenClaims:
    try:
        data = jwt.decode(
            token, secret, algorithms=[ALGORITHM], options={"require": ["sub", "exp", "inst", "role"]}
        )
    except jwt.ExpiredSignatureError as e:
        raise AppError(401, "token_expired", "로그인이 만료되었습니다. 다시 로그인하세요.") from e
    except jwt.InvalidTokenError as e:
        raise AppError(401, "unauthorized", "인증 정보가 올바르지 않습니다.") from e
    return TokenClaims(sub=str(data["sub"]), inst=str(data["inst"]), role=str(data["role"]))
