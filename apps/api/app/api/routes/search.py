from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db, get_services
from app.container import Services
from app.core.logging import new_ulid, request_id_var
from app.retrieval.service import SearchResult
from app.schemas.search import Hit, SearchRequest, SearchResponse
from app.storage.models import QueryLog, User

router = APIRouter(tags=["search"])
log = logging.getLogger(__name__)


def record_query(
    db: Session,
    services: Services,
    user: User,
    result: SearchResult,
    query: str,
    *,
    timings: dict[str, float] | None = None,
    provider: str | None = None,
    model: str | None = None,
    usage: dict[str, int] | None = None,
    abstained: bool = False,
    cache_status: str | None = None,
    degraded: bool | None = None,
) -> None:
    """query_logs 1행. 질문 원문은 LOG_QUERY_TEXT=true 일 때만 저장한다."""
    try:
        db.add(
            QueryLog(
                request_id=request_id_var.get() or new_ulid(),
                user_id=user.id,
                institution_id=user.institution_id,
                mode=result.mode,
                collection_ids=list(result.scope.collection_ids),
                timings_ms=timings or result.timings_ms,
                provider=provider,
                model=model,
                usage=usage,
                cache_status=cache_status or result.cache_status,
                abstained=int(abstained),
                degraded=int(result.degraded if degraded is None else degraded),
                hit_count=len(result.hits),
                query_text=query if services.settings.log_query_text else None,
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001 - 기록 실패가 응답을 막지 않는다
        db.rollback()
        log.exception("query_log_failed", extra={"event": "query_log_failed"})


@router.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> SearchResponse:
    services.ratelimiter.check(user.id, "query")
    result = await services.search.retrieve(db, user, body.query, body.collection_ids, body.mode, body.top_k)
    record_query(db, services, user, result, body.query)
    return SearchResponse(
        request_id=request_id_var.get() or "",
        mode=result.mode,
        modes_used=result.modes_used,
        degraded=result.degraded,
        hits=[Hit(**h.as_dict()) for h in result.hits],
        timings_ms=result.timings_ms,
        cache_status=result.cache_status,
        keyword_analyzer=services.settings.keyword_analyzer,
    )
