"""모드별 검색 orchestration (설계서 6장).

scope 계산 → (keyword | vector | 둘 다 병렬) → RRF·중복 제거 → 원장 재대조 → 페이지 상한 → top_k.
한쪽 엔진 실패 시 hybrid 는 degraded 로 응답하고, 둘 다 실패하거나 단일 모드 엔진이 실패하면 503.

캐시(10.1, ADR-008): 질문 임베딩 → 검색 결과 순으로 본다. degraded 결과는 저장하지 않고,
적중 결과도 원장 대조를 다시 한다.
cache_status: off(둘 다 꺼짐) | miss | embed_hit(임베딩만 적중) | hit(검색 결과 적중).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cache import embedding_key, retrieval_key
from app.core.config import EMBED_QUERY_TIMEOUT_SECONDS
from app.core.errors import AppError
from app.core.scope import Scope, resolve_scope
from app.retrieval.fusion import Fused, cap_per_page, rrf
from app.retrieval.types import Candidate
from app.storage.models import Collection, Document, User
from app.storage.seed import DEFAULT_SEARCH_PROFILE

if TYPE_CHECKING:
    from app.container import Services

log = logging.getLogger(__name__)


@dataclass
class RetrievedHit:
    rank: int
    fused: Fused
    document_title: str

    def as_dict(self) -> dict[str, Any]:
        c = self.fused.chunk
        return {
            "rank": self.rank,
            "chunk_id": c.chunk_id,
            "document_id": c.document_id,
            "document_title": self.document_title,
            "collection_id": c.collection_id,
            "page_number": c.page_number,
            "ordinal": c.ordinal,
            "text": c.text,
            "score": round(self.fused.score, 6),
            "keyword_rank": self.fused.keyword_rank,
            "vector_rank": self.fused.vector_rank,
        }


@dataclass
class SearchResult:
    scope: Scope
    mode: str
    modes_used: list[str]
    degraded: bool
    hits: list[RetrievedHit]
    profile: dict[str, Any]
    timings_ms: dict[str, float] = field(default_factory=dict)
    cache_status: str = "off"


class _Timer:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.ms: dict[str, float] = {}
        self.embed_hit = False

    def lap(self, name: str, since: float) -> float:
        now = time.perf_counter()
        self.ms[name] = round((now - since) * 1000, 1)
        return now

    def total(self) -> None:
        self.ms["total"] = round((time.perf_counter() - self.t0) * 1000, 1)


def search_profile(db: Session, scope: Scope, requested: list[str]) -> dict[str, Any]:
    """첫 요청 컬렉션(없으면 slug 순 첫 허용 컬렉션)의 검색 프로필을 쓴다."""
    if not scope.collection_ids:
        return dict(DEFAULT_SEARCH_PROFILE)
    cols = {c.id: c for c in db.scalars(select(Collection).where(Collection.id.in_(scope.collection_ids)))}
    first = cols.get(requested[0]) if requested else min(cols.values(), key=lambda c: c.slug)
    return {**DEFAULT_SEARCH_PROFILE, **((first.search_profile if first else None) or {})}


def ledger_check(db: Session, scope: Scope, items: list[Fused]) -> tuple[list[Fused], dict[str, str]]:
    """원장 재대조 (6.4): ready 이고 active_version 이 일치하며 scope 안인 청크만 남긴다.
    반환: (남은 후보, document_id → 원본 파일명)."""
    if not items:
        return [], {}
    doc_ids = {f.chunk.document_id for f in items}
    docs = {d.id: d for d in db.scalars(select(Document).where(Document.id.in_(doc_ids)))}
    allowed = set(scope.collection_ids)
    kept: list[Fused] = []
    stale = out_of_scope = 0
    for f in items:
        c = f.chunk
        d = docs.get(c.document_id)
        if (
            c.collection_id not in allowed
            or c.institution_id != scope.institution_id
            or (d is not None and d.collection_id not in allowed)
        ):
            out_of_scope += 1
            continue
        if d is None or d.status != "ready" or d.active_version != c.document_version:
            stale += 1
            continue
        kept.append(f)
    if out_of_scope:
        log.warning(
            "search_out_of_scope_removed",
            extra={"event": "search_out_of_scope_removed", "count": out_of_scope},
        )
    if stale:
        log.info("search_stale_removed", extra={"event": "search_stale_removed", "count": stale})
    return kept, {d.id: d.original_filename for d in docs.values()}


class SearchService:
    def __init__(self, services: Services) -> None:
        self.s = services

    @property
    def engine_timeout(self) -> float:
        return self.s.settings.search_engine_timeout_ms / 1000

    async def _embed(self, query: str) -> tuple[list[float], bool]:
        """(벡터, 캐시 적중 여부). 미적중은 QueryBatcher 로 동시 질문과 묶어 인코딩한다."""
        cache = self.s.cache
        key = embedding_key(self.s.embedder.model, query) if cache.embed_enabled else ""
        if key and (cached := cache.embeddings.get(key)) is not None:
            return list(cached), True
        vec: list[float] = await asyncio.wait_for(
            self.s.query_batcher.embed(query), EMBED_QUERY_TIMEOUT_SECONDS
        )
        if key:
            cache.embeddings[key] = vec
        return vec, False

    async def _vector(self, query: str, scope: Scope, k: int, timer: _Timer) -> list[Candidate]:
        t = time.perf_counter()
        vec, timer.embed_hit = await self._embed(query)
        t = timer.lap("embed_query", t)
        out: list[Candidate] = await asyncio.wait_for(
            self.s.vector.search(
                self.s.vector_collection, vec, scope.institution_id, list(scope.collection_ids), k
            ),
            self.engine_timeout,
        )
        timer.lap("vector", t)
        return out

    async def _keyword(self, query: str, scope: Scope, k: int, timer: _Timer) -> list[Candidate]:
        t = time.perf_counter()
        out: list[Candidate] = await asyncio.wait_for(
            self.s.keyword.search(query, scope.institution_id, list(scope.collection_ids), k),
            self.engine_timeout,
        )
        timer.lap("keyword", t)
        return out

    async def retrieve(
        self,
        db: Session,
        user: User,
        query: str,
        requested: list[str],
        mode: str | None,
        top_k: int | None = None,
        profile_override: dict[str, Any] | None = None,
    ) -> SearchResult:
        timer = _Timer()
        t = time.perf_counter()
        scope = resolve_scope(db, user, requested)
        profile = {**search_profile(db, scope, requested), **(profile_override or {})}
        timer.lap("scope", t)
        mode = mode or profile["mode"]
        k = int(profile["candidate_k"])
        limit = top_k or int(profile["context_k"])

        cache = self.s.cache
        cache_on = cache.embed_enabled or cache.retrieval_enabled
        if not scope.collection_ids:
            timer.total()
            return SearchResult(scope, mode, [], False, [], profile, timer.ms, "miss" if cache_on else "off")

        rkey = (
            retrieval_key(
                query,
                mode,
                k,
                limit,
                int(profile["rrf_rank_constant"]),
                int(profile["max_chunks_per_page"]),
                self.s.index_profile_id,
                self.s.settings.keyword_analyzer,
                scope.fingerprint,
            )
            if cache.retrieval_enabled
            else ""
        )
        if rkey and (cached := cache.retrieval.get(rkey)) is not None:
            t = time.perf_counter()
            cached_modes, cached_items = cached
            kept, titles = ledger_check(db, scope, cached_items)  # 적중도 원장 대조 (10.1 이중 안전장치)
            timer.lap("ledger_check", t)
            hits = [
                RetrievedHit(rank=i, fused=f, document_title=titles.get(f.chunk.document_id, ""))
                for i, f in enumerate(kept, start=1)
            ]
            timer.total()
            return SearchResult(scope, mode, list(cached_modes), False, hits, profile, timer.ms, "hit")

        engines: list[str] = ["keyword", "vector"] if mode == "hybrid" else [mode]
        calls = {
            "keyword": lambda: self._keyword(query, scope, k, timer),
            "vector": lambda: self._vector(query, scope, k, timer),
        }
        results = await asyncio.gather(*(calls[e]() for e in engines), return_exceptions=True)
        got: dict[str, list[Candidate]] = {}
        for name, res in zip(engines, results, strict=True):
            if isinstance(res, BaseException):
                log.warning(
                    "search_engine_failed",
                    extra={"event": "search_engine_failed", "engine": name, "error": repr(res)[:300]},
                )
            else:
                got[name] = res
        if not got:
            raise AppError(503, "search_unavailable", "검색 엔진에 연결할 수 없습니다.", retryable=True)
        modes_used = [e for e in engines if e in got]
        degraded = len(modes_used) < len(engines)

        t = time.perf_counter()
        fused = rrf(got.get("keyword"), got.get("vector"), int(profile["rrf_rank_constant"]))
        t = timer.lap("fusion", t)
        kept, titles = ledger_check(db, scope, fused)
        kept = cap_per_page(kept, int(profile["max_chunks_per_page"]))[:limit]
        timer.lap("ledger_check", t)
        if rkey and not degraded:  # 부분 장애 결과는 엔진 복구 후에도 남지 않도록 저장하지 않는다
            cache.retrieval[rkey] = (tuple(modes_used), list(kept))
        hits = [
            RetrievedHit(rank=i, fused=f, document_title=titles.get(f.chunk.document_id, ""))
            for i, f in enumerate(kept, start=1)
        ]
        timer.total()
        status = "embed_hit" if timer.embed_hit else ("miss" if cache_on else "off")
        return SearchResult(scope, mode, modes_used, degraded, hits, profile, timer.ms, status)
