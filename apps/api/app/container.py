"""앱 전역 의존성 묶음. lifespan 에서 만들고 app.state.services 에 둔다. 테스트는 fake 로 교체한다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.ratelimit import RateLimiter
from app.retrieval.embeddings.base import EmbeddingProvider
from app.storage.db import Database


@dataclass
class Services:
    settings: Settings
    db: Database
    embedder: EmbeddingProvider
    vector: Any
    keyword: Any
    ratelimiter: RateLimiter


def build_embedder(settings: Settings) -> EmbeddingProvider:
    from app.retrieval.embeddings.local_st import LocalSTEmbedding

    return LocalSTEmbedding(settings.embedding_model, batch_size=settings.embedding_batch_size)


def build_services(settings: Settings) -> Services:
    from app.retrieval.keyword import OpenSearchStore
    from app.retrieval.vector import QdrantStore

    return Services(
        settings=settings,
        db=Database(settings.db_url),
        embedder=build_embedder(settings),
        vector=QdrantStore(settings.qdrant_url, settings.search_engine_timeout_ms),
        keyword=OpenSearchStore(
            settings.opensearch_url, settings.search_engine_timeout_ms, settings.keyword_analyzer
        ),
        ratelimiter=RateLimiter(settings),
    )
