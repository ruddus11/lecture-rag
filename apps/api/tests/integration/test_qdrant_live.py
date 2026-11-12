from __future__ import annotations

import pytest

from app.documents.chunker import chunk_id
from app.retrieval.types import ChunkDoc

pytestmark = pytest.mark.integration


def _docs(doc: str, inst: str, col: str, version: int, n: int = 3) -> list[ChunkDoc]:
    return [
        ChunkDoc(chunk_id(doc, version, p, 0), doc, col, inst, version, p, 0, f"{doc} page {p}")
        for p in range(1, n + 1)
    ]


def _vec(i: int) -> list[float]:
    v = [0.0] * 8
    v[i % 8] = 1.0
    return v


async def test_payload_indexes_filter_count_delete(qdrant):
    store, name = qdrant
    await store.ensure_collection(name, 8)
    assert await store.payload_indexes(name) == [
        "collection_id",
        "document_id",
        "document_version",
        "institution_id",
    ]
    a1, a2, b1 = (
        _docs("da", "campus_a", "ca", 1),
        _docs("da", "campus_a", "ca", 2),
        _docs("db", "campus_b", "cb", 1),
    )
    for docs in (a1, a2, b1):
        await store.upsert(name, docs, [_vec(i) for i in range(len(docs))])
    assert await store.count_document(name, "da", 1) == 3 and await store.count_document(name, "da") == 6

    hits = await store.search(name, _vec(0), "campus_b", ["cb"], 10)
    assert hits and {h.chunk.institution_id for h in hits} == {"campus_b"}
    assert await store.search(name, _vec(0), "campus_b", ["ca"], 10) == []  # 기관·컬렉션 둘 다 걸린다

    await store.delete_document(name, "da", below_version=2)
    assert await store.count_document(name, "da", 1) == 0 and await store.count_document(name, "da", 2) == 3
    await store.delete_document(name, "da")
    assert await store.count_document(name, "da") == 0 and await store.count_document(name, "db") == 3
