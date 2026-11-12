"""앱 전역 의존성 묶음. lifespan 에서 만들고 app.state.services 에 둔다. 테스트는 fake 로 교체한다."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.core.config import CHUNKER_VERSION, OPENSEARCH_INDEX, PARSER_VERSION, Settings
from app.core.ratelimit import RateLimiter
from app.documents.chunker import Chunker
from app.retrieval.embeddings.base import EmbeddingProvider, model_slug
from app.retrieval.embeddings.cache import EmbeddingFileCache
from app.storage.db import Database
from app.storage.files import FileStore

if TYPE_CHECKING:
    from app.documents.jobs import JobRunner
    from app.retrieval.service import SearchService


@dataclass
class Services:
    settings: Settings
    db: Database
    embedder: EmbeddingProvider
    vector: Any
    keyword: Any
    ratelimiter: RateLimiter
    files: FileStore = field(init=False)
    chunker: Chunker = field(init=False)
    doc_embedder: EmbeddingFileCache = field(init=False)
    runner: JobRunner | None = None
    search: SearchService = field(init=False)

    def __post_init__(self) -> None:
        from app.retrieval.service import SearchService

        self.files = FileStore(self.settings.data_dir)
        self.chunker = Chunker()
        self.doc_embedder = EmbeddingFileCache(self.settings.emb_cache_dir, self.embedder)
        self.search = SearchService(self)

    # --- 색인 프로필 (설계서 4.2, 5.4) ----------------------------------------
    @property
    def vector_collection(self) -> str:
        """`chunks__{model_slug}__{dim}`. dim 을 모르는 모델은 적재 후에야 정해진다."""
        if not self.embedder.dim:
            self.embedder.load()
        return f"chunks__{model_slug(self.embedder.model)}__{self.embedder.dim}"

    @property
    def keyword_index(self) -> str:
        return OPENSEARCH_INDEX

    @property
    def index_profile_id(self) -> str:
        return (
            f"{self.embedder.name}:{model_slug(self.embedder.model)}:{self.embedder.dim}"
            f"|{self.keyword_index}|chunker-{CHUNKER_VERSION}|{PARSER_VERSION}"
        )

    def invalidate_caches(self) -> None:
        """문서 활성화·삭제 시 호출. 캐시 키에 scope_fingerprint 가 있어 자연 무효화되지만 이중 안전장치."""
        cache = getattr(self, "cache", None)
        if cache is not None:
            cache.clear()

    def embed_query(self, text: str) -> list[float]:
        return self.embedder.embed_query(text)


def build_embedder(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "openai":
        from app.retrieval.embeddings.openai_emb import OpenAIEmbedding

        return OpenAIEmbedding(settings.openai_api_key.get_secret_value(), settings.openai_embedding_model)
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
