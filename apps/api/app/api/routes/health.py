from __future__ import annotations

import asyncio
import logging
import sqlite3
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import CHUNKER_VERSION, PARSER_VERSION

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
        conn = sqlite3.connect(settings.data_dir / "app.db", timeout=2)
        conn.execute("select 1")
        conn.close()
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
    checks["embedding_model"] = services.embedder.is_loaded()

    failed = [k for k, v in checks.items() if v is False]
    body: dict[str, Any] = {"status": "ok" if not failed else "degraded", "checks": checks}
    if errors:
        body["errors"] = errors
    return JSONResponse(body, status_code=200 if not failed else 503)


@router.get("/meta")
async def meta(request: Request) -> dict[str, Any]:
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
        "answer": {"provider": s.answer_provider, "model": None},
        "keyword_analyzer": s.keyword_analyzer,
        "chunker_version": CHUNKER_VERSION,
        "parser_version": PARSER_VERSION,
    }
