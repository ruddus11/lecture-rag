from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import COLLECTION_IDS_MAX, QUERY_MAX_CHARS, QUERY_MIN_CHARS, TOP_K_MAX, TOP_K_MIN
from app.documents.normalize import normalize_query

Mode = Literal["keyword", "vector", "hybrid"]


class SearchRequest(BaseModel):
    query: str = Field(
        min_length=QUERY_MIN_CHARS,
        max_length=QUERY_MAX_CHARS,
        description=f"질문 {QUERY_MIN_CHARS}~{QUERY_MAX_CHARS}자 (NFC, 공백 정리 후 기준)",
    )
    collection_ids: list[str] = Field(default_factory=list, max_length=COLLECTION_IDS_MAX)
    mode: Mode | None = Field(None, description="생략하면 컬렉션 검색 프로필의 mode")
    top_k: int = Field(10, ge=TOP_K_MIN, le=TOP_K_MAX)

    @field_validator("query")
    @classmethod
    def _normalize(cls, v: str) -> str:
        v = normalize_query(v)
        if not (QUERY_MIN_CHARS <= len(v) <= QUERY_MAX_CHARS):
            raise ValueError(f"query 는 공백 정리 후 {QUERY_MIN_CHARS}~{QUERY_MAX_CHARS}자여야 합니다.")
        return v


class Hit(BaseModel):
    rank: int
    chunk_id: str
    document_id: str
    document_title: str
    collection_id: str
    page_number: int
    ordinal: int
    text: str
    score: float
    keyword_rank: int | None = None
    vector_rank: int | None = None


class SearchResponse(BaseModel):
    request_id: str
    mode: str
    modes_used: list[str]
    degraded: bool
    hits: list[Hit]
    timings_ms: dict[str, float]
    cache_status: str
    keyword_analyzer: str
