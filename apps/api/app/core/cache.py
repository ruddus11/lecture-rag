"""M8 캐시 골격. TTL 0이면 저장하지 않으며 실제 검색 연결은 M10에서 한다."""

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
        self.embeddings: TTLCache[str, Any] = TTLCache(maxsize=2000, ttl=max(0, embed_ttl))
        self.retrieval: TTLCache[str, Any] = TTLCache(maxsize=1000, ttl=max(0, retrieval_ttl))

    def clear(self) -> None:
        self.embeddings.clear()
        self.retrieval.clear()
