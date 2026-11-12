"""허용 컬렉션 계산 (설계서 6.1, 9.2). 모든 조회·검색·파일·캐시가 이 결과를 쓴다."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import collection_not_found
from app.storage.models import Collection, User


@dataclass(frozen=True)
class Scope:
    institution_id: str
    collection_ids: tuple[str, ...]
    versions: tuple[tuple[str, int], ...]

    @property
    def fingerprint(self) -> str:
        items = ",".join(f"{cid}:{ver}" for cid, ver in sorted(self.versions))
        return hashlib.sha256(items.encode()).hexdigest()


def permitted_collections(db: Session, user: User) -> list[Collection]:
    rows = db.scalars(
        select(Collection).where(Collection.institution_id == user.institution_id).order_by(Collection.slug)
    ).all()
    return [c for c in rows if user.role in (c.allowed_roles or [])]


def resolve_scope(db: Session, user: User, requested: list[str] | None = None) -> Scope:
    """요청이 비면 허용 전체, 허용 밖 ID가 하나라도 있으면 404 (타 기관 존재를 노출하지 않음)."""
    permitted = {c.id: c for c in permitted_collections(db, user)}
    if requested:
        wanted = list(dict.fromkeys(requested))
        if any(cid not in permitted for cid in wanted):
            raise collection_not_found()
        chosen = [permitted[cid] for cid in wanted]
    else:
        chosen = list(permitted.values())
    chosen.sort(key=lambda c: c.id)
    return Scope(
        institution_id=user.institution_id,
        collection_ids=tuple(c.id for c in chosen),
        versions=tuple((c.id, c.version) for c in chosen),
    )


def check_collection_access(db: Session, user: User, collection_id: str) -> Collection:
    """단일 컬렉션 접근 확인. 허용 밖이면 404."""
    col = db.get(Collection, collection_id)
    if col is None or col.institution_id != user.institution_id or user.role not in (col.allowed_roles or []):
        raise collection_not_found()
    return col
