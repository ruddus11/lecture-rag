"""질문 임베딩·검색 결과 TTL 캐시 (설계서 10.1, ADR-008). TTL 0이면 해당 캐시를 쓰지 않는다.

검색 결과 키에는 scope_fingerprint(허용 컬렉션 id:version)가 들어가 다른 권한 범위나 이전 문서 버전의 결과를
읽을 수 없다. 문서 활성화·삭제 시 전체 clear() 하고, 적중 결과도 원장 대조를 다시 거친다
(retrieval/service.py).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from cachetools import TTLCache

from app.documents.normalize import normalize_query


def embedding_key(model: str, query: str) -> str:
    return hashlib.sha256(f"{model}\x00{normalize_query(query)}".encode()).hexdigest()


def retrieval_key(
    query: str,
    mode: str,
    candidate_k: int,
    context_k: int,
    rrf_k: int,
    max_chunks_per_page: int,
    index_profile_id: str,
    keyword_analyzer: str,
    scope_fingerprint: str,
) -> str:
    parts = [
        normalize_query(query),
        mode,
        candidate_k,
        context_k,
        rrf_k,
        max_chunks_per_page,
        index_profile_id,
        keyword_analyzer,
        scope_fingerprint,
    ]
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


class CacheStore:
    def __init__(self, embed_ttl: int = 0, retrieval_ttl: int = 0) -> None:
        self.embed_enabled = embed_ttl > 0
        self.retrieval_enabled = retrieval_ttl > 0
        self.embeddings: TTLCache[str, Any] = TTLCache(maxsize=2000, ttl=max(0, embed_ttl))
        self.retrieval: TTLCache[str, Any] = TTLCache(maxsize=1000, ttl=max(0, retrieval_ttl))

    def clear(self) -> None:
        self.embeddings.clear()
        self.retrieval.clear()
