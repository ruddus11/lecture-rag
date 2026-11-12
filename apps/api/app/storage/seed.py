"""yaml 정책 선언 → SQLite 원장 upsert (설계서 4.4). 권한 판단은 항상 원장으로 한다."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.db import Database
from app.storage.models import Collection, Institution, User

log = logging.getLogger(__name__)

DEFAULT_SEARCH_PROFILE: dict[str, Any] = {
    "mode": "hybrid",
    "candidate_k": 20,
    "context_k": 5,
    "rrf_rank_constant": 60,
    "max_chunks_per_page": 2,
}


def _resolve(path: Path) -> Path:
    """실제 파일이 없으면 같은 폴더의 *.example.yaml 을 쓴다 (fresh clone 기동용)."""
    if path.exists():
        return path
    example = path.with_name(path.stem + ".example" + path.suffix)
    if example.exists():
        log.warning("seed_using_example", extra={"event": "seed_using_example", "file": str(example)})
        return example
    raise FileNotFoundError(path)


def seed_from_files(db: Database, institutions_file: Path, users_file: Path) -> dict[str, int]:
    inst_doc = yaml.safe_load(_resolve(institutions_file).read_text(encoding="utf-8")) or {}
    user_doc = yaml.safe_load(_resolve(users_file).read_text(encoding="utf-8")) or {}
    with db.session() as s:
        stats = seed(s, inst_doc.get("institutions", {}), user_doc.get("users", []))
        s.commit()
    log.info("seed_done", extra={"event": "seed_done", **stats})
    return stats


def seed(s: Session, institutions: dict[str, Any], users: list[dict[str, Any]]) -> dict[str, int]:
    stats = {"institutions": 0, "collections": 0, "users": 0}
    for inst_id, spec in institutions.items():
        inst = s.get(Institution, inst_id)
        if inst is None:
            s.add(Institution(id=inst_id, name=spec.get("name", inst_id)))
        else:
            inst.name = spec.get("name", inst.name)
        stats["institutions"] += 1
        profile = {**DEFAULT_SEARCH_PROFILE, **(spec.get("search") or {})}
        for c in spec.get("collections", []):
            col = s.scalar(
                select(Collection).where(Collection.institution_id == inst_id, Collection.slug == c["slug"])
            )
            roles = list(c.get("allowed_roles") or ["student", "admin"])
            col_profile = {**profile, **(c.get("search") or {})}
            if col is None:
                s.add(
                    Collection(
                        id=str(uuid.uuid4()),
                        institution_id=inst_id,
                        slug=c["slug"],
                        name=c.get("name", c["slug"]),
                        allowed_roles=roles,
                        search_profile=col_profile,
                        version=1,
                    )
                )
            else:  # version 은 유지
                col.name = c.get("name", col.name)
                col.allowed_roles = roles
                col.search_profile = col_profile
            stats["collections"] += 1
    s.flush()
    for u in users:
        row = s.scalar(select(User).where(User.username == u["username"]))
        if row is None:
            s.add(
                User(
                    id=str(uuid.uuid4()),
                    username=u["username"],
                    password_hash=u["password_hash"],
                    institution_id=u["institution"],
                    role=u["role"],
                )
            )
        else:
            row.password_hash = u["password_hash"]
            row.institution_id = u["institution"]
            row.role = u["role"]
        stats["users"] += 1
    return stats
