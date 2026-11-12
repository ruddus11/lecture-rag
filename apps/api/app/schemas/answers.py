from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.core.config import COLLECTION_IDS_MAX, QUERY_MAX_CHARS, QUERY_MIN_CHARS
from app.documents.normalize import normalize_query
from app.schemas.search import Hit, Mode


class AnswerRequest(BaseModel):
    query: str = Field(min_length=QUERY_MIN_CHARS, max_length=QUERY_MAX_CHARS)
    collection_ids: list[str] = Field(default_factory=list, max_length=COLLECTION_IDS_MAX)
    mode: Mode | None = Field(None, description="생략하면 컬렉션 검색 프로필의 mode")

    @field_validator("query")
    @classmethod
    def _normalize(cls, v: str) -> str:
        v = normalize_query(v)
        if not (QUERY_MIN_CHARS <= len(v) <= QUERY_MAX_CHARS):
            raise ValueError(f"query 는 공백 정리 후 {QUERY_MIN_CHARS}~{QUERY_MAX_CHARS}자여야 합니다.")
        return v


class CitationOut(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    page_number: int
    quote: str


class ProviderOut(BaseModel):
    name: str
    model: str


class AnswerResponse(BaseModel):
    request_id: str
    mode: str
    abstained: bool
    abstain_reason: str | None
    answer: str
    citations: list[CitationOut]
    hits: list[Hit]
    provider: ProviderOut
    usage: dict[str, int]
    degraded: bool
    modes_used: list[str]
    timings_ms: dict[str, float]
    cache_status: str
    keyword_analyzer: str
