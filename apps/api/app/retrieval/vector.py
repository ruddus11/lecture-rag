"""Qdrant 어댑터 (설계서 4.2, 6.2). 앱 전역 AsyncQdrantClient 1개.

- 컬렉션 이름 `chunks__{model_slug}__{dim}`. 생성 직후 payload index 4개.
- 검색 필터는 institution_id 와 허용 collection_id 목록을 둘 다 넣는다 (9.2 규칙 3).
- url 이 ":memory:" 이면 qdrant-client 로컬 모드(테스트용, payload index 는 효과 없음).
"""

from __future__ import annotations

import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qm

from app.retrieval.embeddings.base import model_slug
from app.retrieval.types import Candidate, ChunkDoc

log = logging.getLogger(__name__)

UPSERT_BATCH = 64
PAYLOAD_INDEXES: dict[str, qm.PayloadSchemaType] = {
    "institution_id": qm.PayloadSchemaType.KEYWORD,
    "collection_id": qm.PayloadSchemaType.KEYWORD,
    "document_id": qm.PayloadSchemaType.KEYWORD,
    "document_version": qm.PayloadSchemaType.INTEGER,
}


def collection_name(model: str, dim: int) -> str:
    return f"chunks__{model_slug(model)}__{dim}"


def scope_filter(institution_id: str, collection_ids: list[str] | tuple[str, ...]) -> qm.Filter:
    return qm.Filter(
        must=[
            qm.FieldCondition(key="institution_id", match=qm.MatchValue(value=institution_id)),
            qm.FieldCondition(key="collection_id", match=qm.MatchAny(any=list(collection_ids))),
        ]
    )


def document_filter(
    document_id: str, version: int | None = None, below_version: int | None = None
) -> qm.Filter:
    must: list[qm.Condition] = [qm.FieldCondition(key="document_id", match=qm.MatchValue(value=document_id))]
    if version is not None:
        must.append(qm.FieldCondition(key="document_version", match=qm.MatchValue(value=version)))
    if below_version is not None:
        must.append(qm.FieldCondition(key="document_version", range=qm.Range(lt=below_version)))
    return qm.Filter(must=must)


class QdrantStore:
    def __init__(self, url: str, timeout_ms: int = 2000) -> None:
        self.url = url
        self.timeout_s = max(1, timeout_ms // 1000)
        if url == ":memory:":
            self.client = AsyncQdrantClient(location=":memory:")
        else:
            self.client = AsyncQdrantClient(url=url, timeout=self.timeout_s, check_compatibility=False)
        self.filters_enabled = True  # 테스트 전용: False 면 검색 필터를 빼고 원장 대조만으로 막히는지 본다
        self._ensured: set[str] = set()

    async def ping(self) -> bool:
        await self.client.get_collections()
        return True

    async def ensure_collection(self, name: str, dim: int) -> None:
        if name in self._ensured:
            return
        if not await self.client.collection_exists(name):
            try:
                await self.client.create_collection(
                    name, vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE)
                )
                log.info(
                    "qdrant_collection_created", extra={"event": "qdrant_collection_created", "name": name}
                )
            except Exception:
                if not await self.client.collection_exists(name):  # 동시 생성 경합이면 통과
                    raise
        if self.url != ":memory:":
            existing = set((await self.client.get_collection(name)).payload_schema or {})
            for field, schema in PAYLOAD_INDEXES.items():
                if field not in existing:
                    await self.client.create_payload_index(
                        name, field_name=field, field_schema=schema, wait=True
                    )
        self._ensured.add(name)

    async def payload_indexes(self, name: str) -> list[str]:
        if not await self.client.collection_exists(name):
            return []
        return sorted((await self.client.get_collection(name)).payload_schema or {})

    async def collections(self) -> list[str]:
        return [c.name for c in (await self.client.get_collections()).collections]

    async def upsert(self, name: str, docs: list[ChunkDoc], vectors: list[list[float]]) -> None:
        for i in range(0, len(docs), UPSERT_BATCH):
            points = [
                qm.PointStruct(id=d.chunk_id, vector=v, payload=d.payload())
                for d, v in zip(docs[i : i + UPSERT_BATCH], vectors[i : i + UPSERT_BATCH], strict=True)
            ]
            await self.client.upsert(name, points=points, wait=True)

    async def count(self, name: str, flt: qm.Filter | None = None) -> int:
        if not await self.client.collection_exists(name):
            return 0
        return (await self.client.count(name, count_filter=flt, exact=True)).count

    async def count_document(self, name: str, document_id: str, version: int | None = None) -> int:
        return await self.count(name, document_filter(document_id, version=version))

    async def delete_document(
        self, name: str, document_id: str, version: int | None = None, below_version: int | None = None
    ) -> None:
        if not await self.client.collection_exists(name):
            return
        flt = document_filter(document_id, version=version, below_version=below_version)
        await self.client.delete(name, points_selector=qm.FilterSelector(filter=flt), wait=True)

    async def search(
        self, name: str, vector: list[float], institution_id: str, collection_ids: list[str], limit: int
    ) -> list[Candidate]:
        if not await self.client.collection_exists(name):
            return []
        flt = scope_filter(institution_id, collection_ids) if self.filters_enabled else None
        res = await self.client.query_points(
            name, query=vector, query_filter=flt, limit=limit, with_payload=True
        )
        return [
            Candidate.from_payload(p.payload or {}, rank=i, score=float(p.score))
            for i, p in enumerate(res.points, start=1)
        ]

    async def close(self) -> None:
        await self.client.close()
