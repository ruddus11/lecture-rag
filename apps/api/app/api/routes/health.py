from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from app.api.deps import current_user
from app.core.config import CHUNKER_VERSION, PARSER_VERSION
from app.storage.models import Document, User

router = APIRouter(tags=["health"])
log = logging.getLogger(__name__)


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


async def _check(coro: Any, timeout: float = 3.0) -> tuple[bool, Any]:
    try:
        return True, await asyncio.wait_for(coro, timeout)
    except Exception as e:  # noqa: BLE001 - readiness 는 실패 이유만 기록
        log.warning("ready_check_failed", extra={"event": "ready_check_failed", "error": repr(e)})
        return False, None


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    services = request.app.state.services
    settings = services.settings
    checks: dict[str, Any] = {}
    errors: list[str] = []

    try:
        with services.db.engine.connect() as conn:
            conn.execute(text("select 1"))
        checks["sqlite"] = True
    except Exception:  # noqa: BLE001
        checks["sqlite"] = False

    checks["qdrant"], _ = await _check(services.vector.ping())
    checks["opensearch"], _ = await _check(services.keyword.health())
    if settings.keyword_analyzer == "korean":
        ok, has = await _check(services.keyword.has_nori())
        checks["nori"] = bool(ok and has)
        if not checks["nori"]:
            errors.append("keyword_analyzer_missing")
    else:
        checks["nori"] = "skipped(analyzer=standard)"
    if checks["opensearch"]:
        _, fields = await _check(services.keyword.keyword_fields())
        checks["opensearch_keyword_fields"] = fields or []
    checks["embedding_model"] = services.embedder.is_loaded()
    warnings: list[str] = []
    if checks["embedding_model"] and checks["qdrant"]:
        name = services.vector_collection
        ok, _ = await _check(services.vector.ensure_collection(name, services.embedder.dim))
        checks["qdrant_collection"] = name if ok else False
        _, idx = await _check(services.vector.payload_indexes(name))
        checks["qdrant_payload_indexes"] = idx or []
        if ok and await _reindex_required(services, name):
            warnings.append("reindex_required")
            log.warning("reindex_required", extra={"event": "reindex_required", "collection": name})

    failed = [k for k, v in checks.items() if v is False]
    body: dict[str, Any] = {"status": "ok" if not failed else "degraded", "checks": checks}
    if errors:
        body["errors"] = errors
    if warnings:
        body["warnings"] = warnings
    return JSONResponse(body, status_code=200 if not failed else 503)


async def _reindex_required(services: Any, name: str) -> bool:
    """ready 문서가 있는데 현재 임베딩 컬렉션이 비어 있으면 다른 모델로 색인된 것이다 (설계서 5.4)."""
    with services.db.session() as s:
        ready = s.scalar(select(func.count()).select_from(Document).where(Document.status == "ready")) or 0
    if not ready:
        return False
    ok, n = await _check(services.vector.count(name))
    return bool(ok and n == 0)


@router.get("/meta")
async def meta(request: Request, _: User = Depends(current_user)) -> dict[str, Any]:
    services = request.app.state.services
    s = services.settings
    return {
        "version": request.app.version,
        "commit": s.app_commit,
        "embedding": {
            "provider": services.embedder.name,
            "model": services.embedder.model,
            "dim": services.embedder.dim,
        },
        "answer": {"provider": services.answer_provider.name, "model": services.answer_provider.model},
        "index_profile": {
            "id": services.index_profile_id,
            "qdrant_collection": services.vector_collection if services.embedder.dim else None,
            "opensearch_index": services.keyword_index,
        },
        "keyword_analyzer": s.keyword_analyzer,
        "chunker_version": CHUNKER_VERSION,
        "parser_version": PARSER_VERSION,
    }
