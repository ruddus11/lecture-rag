"""AnswerProvider 인터페이스와 공통 결과 타입 (설계서 7.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Evidence:
    local_id: str  # "c1".."cN", LLM 에 노출되는 ID
    chunk_id: str
    document_id: str
    document_title: str
    page_number: int
    text: str


class Citation(BaseModel):
    local_id: str = Field(description="근거 id (c1, c2 ...)")
    quote: str = Field(description="그 근거에서 그대로 복사한 문장")


class AnswerDraft(BaseModel):
    """LLM 구조화 출력 스키마."""

    insufficient_evidence: bool
    answer: str = Field(description="insufficient_evidence 이면 빈 문자열")
    citations: list[Citation]


@dataclass
class ProviderResult:
    draft: AnswerDraft | None
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: int = 0
    refused: bool = False


class ProviderError(Exception):
    """공급자 호출 실패. status 는 API 로 낼 HTTP 상태(429/503/500)."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class AnswerProvider(Protocol):
    name: str
    model: str

    async def generate(self, question: str, evidences: list[Evidence]) -> ProviderResult: ...
