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
    # 필터 필드 keyword 매핑 (설계서 10.2-4). document_version 은 integer
    fields = set(await s.keyword.keyword_fields())
    assert {"chunk_id", "collection_id", "document_id", "institution_id"} <= fields

    for mode in ("keyword", "vector", "hybrid"):
        r = await it_api.search("a_student", Q, mode=mode)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["hits"] and body["hits"][0]["page_number"] == 3, (mode, body["hits"][:2])
    assert body["modes_used"] == ["keyword", "vector"]
    assert (await it_api.search("b_student", Q, mode="hybrid")).json()["hits"] == []

    deleted = await it_api.c.delete(
        f"/api/v1/documents/{up['document_id']}", headers=await it_api.h("a_admin")
    )
    assert deleted.status_code == 202
    # 두 엔진에 데이터가 남아 있는 동안에도 차단한다.
    assert (await it_api.search("a_student", Q, mode="hybrid")).json()["hits"] == []
    await it_api.drain()
    assert await s.vector.count_document(s.vector_collection, up["document_id"]) == 0
    assert await s.keyword.count_document(up["document_id"]) == 0
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


async def test_retry_purges_old_versions_live(it_api, pdfs):
    from app.storage.models import Document

    up = await it_api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    did = up["document_id"]
    with it_api.services.db.session() as db:
        db.get(Document, did).status = "failed"
        db.commit()
    r = await it_api.c.post(
        f"/api/v1/documents/{did}/retry", headers=await it_api.h("a_admin"), json={"expected_version": 1}
    )
    assert r.status_code == 202
    await it_api.drain()
    s = it_api.services
    assert await s.vector.count_document(s.vector_collection, did, 1) == 0
    assert await s.keyword.count_document(did, 1) == 0
    assert await s.vector.count_document(s.vector_collection, did, 2) > 0
    assert await s.keyword.count_document(did, 2) > 0
