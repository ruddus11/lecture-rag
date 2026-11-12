"""실제 엔진으로 ingest → 세 모드 → 엔진 삭제 → 0건, OpenSearch 중단 시 degraded."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

Q = "교착 상태의 네 가지 필요 조건"


async def test_ingest_three_modes_then_delete(it_api, pdfs):
    up = await it_api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    s = it_api.services
    doc = (
        await it_api.c.get(f"/api/v1/documents/{up['document_id']}", headers=await it_api.h("a_admin"))
    ).json()
    assert doc["status"] == "ready", doc
    n = doc["chunk_count"]
    assert await s.keyword.count_document(up["document_id"], 1) == n
    assert await s.vector.count_document(s.vector_collection, up["document_id"], 1) == n

    for mode in ("keyword", "vector", "hybrid"):
        r = await it_api.search("a_student", Q, mode=mode)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["hits"] and body["hits"][0]["page_number"] == 3, (mode, body["hits"][:2])
    assert body["modes_used"] == ["keyword", "vector"]
    assert (await it_api.search("b_student", Q, mode="hybrid")).json()["hits"] == []

    await s.vector.delete_document(s.vector_collection, up["document_id"])
    await s.keyword.delete_document(up["document_id"])
    for mode in ("keyword", "vector", "hybrid"):
        assert (await it_api.search("a_student", Q, mode=mode)).json()["hits"] == []


async def test_opensearch_unreachable_degraded(it_api, pdfs):
    await it_api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    from app.retrieval.keyword import OpenSearchStore

    s = it_api.services
    real = s.keyword
    down = OpenSearchStore("http://127.0.0.1:9", 1000)  # 닫힌 포트 = 중단된 OpenSearch
    down.index = real.index
    s.keyword = down
    try:
        r = await it_api.search("a_student", Q, mode="hybrid")
        assert r.status_code == 200 and r.json()["degraded"] is True and r.json()["modes_used"] == ["vector"]
        assert (await it_api.search("a_student", Q, mode="keyword")).status_code == 503
    finally:
        s.keyword = real
        await down.close()
    r = await it_api.search("a_student", Q, mode="hybrid")
    assert r.json()["degraded"] is False


async def test_nori_analyzer_live(it_api):
    kw = it_api.services.keyword
    await kw.ensure_index()
    assert await kw.has_nori()
    assert await kw.analyze("TCP 혼잡 제어") == ["tcp", "혼잡", "제어"]
    assert "수" not in await kw.analyze("프로세스를 종료할 수 있다")  # NNB 제거 (ADR-004)
