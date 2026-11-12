"""검색 엔진 어댑터가 주고받는 값 (keyword·vector 공통 payload, 설계서 4.2·4.3)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ChunkDoc:
    """색인 단위. Qdrant payload 와 OpenSearch _source 의 고정 키."""

    chunk_id: str
    document_id: str
    collection_id: str
    institution_id: str
    document_version: int
    page_number: int
    ordinal: int
    text: str

    def payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Candidate:
    """엔진 한 곳의 검색 결과 1건. rank 는 1부터."""

    chunk: ChunkDoc
    rank: int
    score: float

    @staticmethod
    def from_payload(p: dict[str, Any], rank: int, score: float) -> Candidate:
        return Candidate(
            chunk=ChunkDoc(
                chunk_id=str(p["chunk_id"]),
                document_id=str(p["document_id"]),
                collection_id=str(p["collection_id"]),
                institution_id=str(p["institution_id"]),
                document_version=int(p["document_version"]),
                page_number=int(p["page_number"]),
                ordinal=int(p["ordinal"]),
                text=str(p["text"]),
            ),
            rank=rank,
            score=score,
        )
