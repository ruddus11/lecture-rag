from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db, get_services
from app.api.routes.search import record_query
from app.container import Services
from app.core.logging import request_id_var
from app.schemas.answers import AnswerRequest, AnswerResponse, CitationOut, ProviderOut
from app.schemas.search import Hit
from app.storage.models import User

router = APIRouter(tags=["answers"])


@router.post("/answers", response_model=AnswerResponse)
async def answers(
    body: AnswerRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> AnswerResponse:
    services.ratelimiter.check(user.id, "query", "answers")
    out = await services.answers.answer(db, user, body.query, body.collection_ids, body.mode)
    record_query(
        db,
        services,
        user,
        out.search,
        body.query,
        timings=out.timings_ms,
        provider=out.provider["name"],
        model=out.provider["model"],
        usage=out.usage,
        abstained=out.abstained,
        degraded=out.degraded,
    )
    return AnswerResponse(
        request_id=request_id_var.get() or "",
        mode=out.search.mode,
        abstained=out.abstained,
        abstain_reason=out.abstain_reason,
        answer=out.answer,
        citations=[CitationOut(**c) for c in out.citations],
        hits=[Hit(**h.as_dict()) for h in out.hits],
        provider=ProviderOut(**out.provider),
        usage=out.usage,
        degraded=out.degraded,
        modes_used=out.search.modes_used,
        timings_ms=out.timings_ms,
        cache_status=out.search.cache_status,
        keyword_analyzer=services.settings.keyword_analyzer,
    )
