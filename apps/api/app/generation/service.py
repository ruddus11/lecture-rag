"""검색 → (0건이면 보류) → 생성 → 인용 검증 → (invalid_citations 면 1회 재생성) → 응답 조립 (설계서 7장).

- 인용과 hits 는 같은 요청에서 검색한 청크 집합에서만 나온다(9.2 규칙 5).
- 공급자 503 계열(연결·5xx·타임아웃)은 보류 + degraded=true 로 hits 만 준다. 429 는 429, 그 밖은 500.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.scope import resolve_scope
from app.generation.base import AnswerProvider, Evidence, ProviderError, ProviderResult
from app.generation.citations import Verdict, verify
from app.retrieval.service import RetrievedHit, SearchResult, ledger_check
from app.storage.models import User

if TYPE_CHECKING:
    from app.container import Services

log = logging.getLogger(__name__)


@dataclass
class AnswerOutcome:
    search: SearchResult
    hits: list[RetrievedHit]
    abstained: bool
    abstain_reason: str | None
    answer: str
    citations: list[dict[str, Any]]
    provider: dict[str, str]
    usage: dict[str, int]
    degraded: bool
    timings_ms: dict[str, float] = field(default_factory=dict)
    attempts: int = 0
    dropped_citations: int = 0


def evidences_from(hits: list[RetrievedHit]) -> list[Evidence]:
    return [
        Evidence(
            local_id=f"c{i}",
            chunk_id=h.fused.chunk.chunk_id,
            document_id=h.fused.chunk.document_id,
            document_title=h.document_title,
            page_number=h.fused.chunk.page_number,
            text=h.fused.chunk.text,
        )
        for i, h in enumerate(hits, start=1)
    ]


def _add_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    for k in ("input_tokens", "output_tokens"):
        total[k] = total.get(k, 0) + int(usage.get(k, 0) or 0)


class AnswerService:
    def __init__(self, services: Services, provider: AnswerProvider) -> None:
        self.s = services
        self.provider = provider

    async def _call(self, question: str, evidences: list[Evidence]) -> ProviderResult:
        timeout = self.s.settings.answer_timeout_seconds
        try:
            return await asyncio.wait_for(self.provider.generate(question, evidences), timeout)
        except TimeoutError:
            raise ProviderError(503, "answer_unavailable", f"답변 생성이 {timeout}초를 넘었습니다.") from None

    async def answer(
        self, db: Session, user: User, query: str, collection_ids: list[str], mode: str | None
    ) -> AnswerOutcome:
        t0 = time.perf_counter()
        result = await self.s.search.retrieve(db, user, query, collection_ids, mode)
        hits = result.hits  # retrieve 의 기본 limit 이 context_k
        timings: dict[str, float] = {"retrieval": result.timings_ms.get("total", 0.0)}
        provider = {"name": self.provider.name, "model": self.provider.model}
        usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

        def done(**kw: Any) -> AnswerOutcome:
            timings["total"] = round((time.perf_counter() - t0) * 1000, 1)
            base: dict[str, Any] = dict(
                search=result,
                hits=hits,
                abstained=True,
                abstain_reason=None,
                answer="",
                citations=[],
                provider=provider,
                usage=usage,
                degraded=result.degraded,
                timings_ms=timings,
            )
            base.update(kw)
            # 생성 대기 중 삭제·권한 변경이 가능하므로 응답 직전 새 원장으로 다시 검사한다.
            with self.s.db.session() as fresh:
                scope = resolve_scope(fresh, user)
                valid, _ = ledger_check(fresh, scope, [h.fused for h in hits])
            allowed = {f.chunk.chunk_id for f in valid}
            if len(allowed) != len(hits):
                base.update(
                    hits=[h for h in hits if h.fused.chunk.chunk_id in allowed],
                    abstained=True,
                    abstain_reason="no_evidence",
                    answer="",
                    citations=[],
                )
            return AnswerOutcome(**base)

        if not hits:  # 7.3-8: LLM 을 부르지 않는다
            return done(abstain_reason="no_evidence")

        evidences = evidences_from(hits)
        max_attempts = max(1, self.s.settings.answer_max_attempts)
        verdict: Verdict | None = None
        gen_ms = verify_ms = 0.0
        attempts = 0
        for attempt in range(1, max_attempts + 1):
            attempts = attempt
            t = time.perf_counter()
            try:
                res = await self._call(query, evidences)
            except ProviderError as e:
                gen_ms += (time.perf_counter() - t) * 1000
                timings["generation"] = round(gen_ms, 1)
                log.warning(
                    "provider_error", extra={"event": "provider_error", "status": e.status, "code": e.code}
                )
                if e.status == 429:
                    raise AppError(
                        429,
                        "provider_rate_limited",
                        "답변 공급자 사용량 한도에 걸렸습니다.",
                        retryable=True,
                        headers={"Retry-After": "30"},
                    ) from e
                if e.status >= 503 or e.status == 502:
                    return done(abstain_reason="provider_unavailable", degraded=True, attempts=attempts)
                raise AppError(500, "provider_error", "답변 생성 중 오류가 발생했습니다.") from e
            gen_ms += (time.perf_counter() - t) * 1000
            provider["model"] = res.model or provider["model"]
            _add_usage(usage, res.usage)
            t = time.perf_counter()
            verdict = verify(res, evidences)
            verify_ms += (time.perf_counter() - t) * 1000
            if verdict.ok or not verdict.retryable:
                break
            log.info(
                "answer_retry", extra={"event": "answer_retry", "reason": verdict.reason, "attempt": attempt}
            )
        timings["generation"] = round(gen_ms, 1)
        timings["verify"] = round(verify_ms, 1)
        assert verdict is not None
        if not verdict.ok:
            return done(abstain_reason=verdict.reason, attempts=attempts, dropped_citations=verdict.dropped)
        citations = [
            {
                "chunk_id": c.evidence.chunk_id,
                "document_id": c.evidence.document_id,
                "document_title": c.evidence.document_title,
                "page_number": c.evidence.page_number,
                "quote": c.quote,
            }
            for c in verdict.citations
        ]
        return done(
            abstained=False,
            answer=verdict.answer,
            citations=citations,
            attempts=attempts,
            dropped_citations=verdict.dropped,
        )
