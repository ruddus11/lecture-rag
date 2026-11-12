"""RRF 융합, chunk 중복 제거, 페이지당 상한 (설계서 6.3, ADR-002).

score(c) = Σ_i 1 / (k + rank_i(c)), rank 는 1부터. 한쪽에만 있으면 그쪽 항만 더한다.
동점은 (vector rank 있음 우선, chunk_id 사전순)으로 결정적으로 정렬한다.
단일 모드도 같은 함수를 지나므로 정렬·중복 제거·페이지 상한 규칙이 세 모드에서 같다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.retrieval.types import Candidate, ChunkDoc


@dataclass
class Fused:
    chunk: ChunkDoc
    score: float
    keyword_rank: int | None = None
    vector_rank: int | None = None


def rrf(keyword: list[Candidate] | None, vector: list[Candidate] | None, k: int = 60) -> list[Fused]:
    by_id: dict[str, Fused] = {}
    for source, items in (("keyword", keyword or []), ("vector", vector or [])):
        seen: set[str] = set()
        for c in sorted(items, key=lambda c: c.rank):
            cid = c.chunk.chunk_id
            if cid in seen:  # 같은 엔진 안의 중복은 첫(최상위) rank 만 쓴다
                continue
            seen.add(cid)
            f = by_id.get(cid)
            if f is None:
                f = by_id[cid] = Fused(chunk=c.chunk, score=0.0)
            f.score += 1.0 / (k + c.rank)
            if source == "keyword":
                f.keyword_rank = c.rank
            else:
                f.vector_rank = c.rank
    return sorted(by_id.values(), key=lambda f: (-f.score, f.vector_rank is None, f.chunk.chunk_id))


def cap_per_page(items: list[Fused], max_per_page: int) -> list[Fused]:
    counts: dict[tuple[str, int], int] = {}
    out: list[Fused] = []
    for f in items:
        key = (f.chunk.document_id, f.chunk.page_number)
        if counts.get(key, 0) >= max_per_page:
            continue
        counts[key] = counts.get(key, 0) + 1
        out.append(f)
    return out
