from __future__ import annotations

from sqlalchemy import select

from app.retrieval.vector import scope_filter
from app.storage.models import Collection, Document, IndexProfile, IngestionJob, QueryLog


async def test_vector_search_returns_relevant_page(api, pdfs):
    up = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    r = await api.search("a_student", "교착 상태의 네 가지 필요 조건은?", mode="vector", top_k=5)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "vector" and body["modes_used"] == ["vector"] and body["degraded"] is False
    assert body["request_id"] == r.headers["x-request-id"]
    hits = body["hits"]
    assert hits and hits[0]["document_id"] == up["document_id"] and hits[0]["page_number"] == 3
    assert hits[0]["document_title"] == "korean_text.pdf" and hits[0]["vector_rank"] == 1
    assert hits[0]["keyword_rank"] is None and [h["rank"] for h in hits] == list(range(1, len(hits) + 1))
    for key in ("scope", "embed_query", "vector", "fusion", "ledger_check", "total"):
        assert key in body["timings_ms"]
    # 페이지당 상한 2
    pages = [(h["document_id"], h["page_number"]) for h in hits]
    assert all(pages.count(p) <= 2 for p in pages)


async def test_qdrant_collection_name_and_index_profile(api, pdfs):
    await api.ingest("a_admin", "ai_basics", pdfs["korean_text.pdf"])
    s = api.services
    assert s.vector_collection == "chunks__fake_embed__256"
    assert "chunks__fake_embed__256" in await s.vector.collections()
    meta = (await api.c.get("/api/v1/meta", headers=await api.h("a_student"))).json()
    assert meta["index_profile"]["qdrant_collection"] == "chunks__fake_embed__256"
    with s.db.session() as db:
        assert db.get(IndexProfile, s.index_profile_id) is not None


async def test_other_institution_gets_zero_and_filter_branch(api, pdfs):
    """b_student 는 campus_a 문서를 받을 수 없다. 필터를 뺀 분기에서는 엔진이 결과를 내지만
    원장 대조(scope 밖 제거)가 막고, 정상 분기에서는 엔진 단계에서 0건이다."""
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    s = api.services
    b_networks = (await api.collections("b_student"))["networks"]
    vec = s.embed_query("교착 상태 필요 조건")

    normal = await s.vector.search(s.vector_collection, vec, "campus_b", [b_networks], 10)
    assert normal == []
    s.vector.filters_enabled = False
    try:
        leaked = await s.vector.search(s.vector_collection, vec, "campus_b", [b_networks], 10)
        assert leaked and all(c.chunk.institution_id == "campus_a" for c in leaked)
        r = await api.search("b_student", "교착 상태 필요 조건", mode="vector")
        assert r.status_code == 200 and r.json()["hits"] == []
    finally:
        s.vector.filters_enabled = True

    a_os = (await api.collections("a_admin"))["operating_systems"]
    r = await api.search("b_student", "교착 상태", mode="vector", collection_ids=[a_os])
    assert r.status_code == 404 and r.json()["error"]["code"] == "collection_not_found"


async def test_role_scope_ta_only(api, pdfs):
    await api.ingest("a_admin", "ta_only", pdfs["korean_text.pdf"])
    assert (await api.search("a_student", "교착 상태", mode="vector")).json()["hits"] == []
    assert (await api.search("a_admin", "교착 상태", mode="vector")).json()["hits"]


async def test_ledger_check_hides_non_ready(api, pdfs):
    up = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    with api.services.db.session() as db:
        db.get(Document, up["document_id"]).status = "deleting"
        db.commit()
    r = await api.search("a_student", "교착 상태", mode="vector")
    assert r.status_code == 200 and r.json()["hits"] == []


async def test_reingest_purges_old_version(api, pdfs):
    up = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    s = api.services
    name = s.vector_collection
    n1 = await s.vector.count_document(name, up["document_id"], 1)
    assert n1 > 0
    with s.db.session() as db:  # 재색인 작업 (scripts/reindex.py 와 같은 방식)
        db.add(IngestionJob(id="job-v2", document_id=up["document_id"], kind="ingest", target_version=2))
        db.commit()
    await api.drain()
    assert await s.vector.count_document(name, up["document_id"], 1) == 0
    assert await s.vector.count_document(name, up["document_id"], 2) == n1
    doc = (await api.c.get(f"/api/v1/documents/{up['document_id']}", headers=await api.h("a_admin"))).json()
    assert doc["active_version"] == 2 and doc["status"] == "ready"
    hits = (await api.search("a_student", "교착 상태", mode="vector")).json()["hits"]
    assert hits and all("job" not in h["chunk_id"] for h in hits)


async def test_search_validation_422(api):
    for body in (
        {"query": ""},
        {"query": "   "},
        {"query": "가" * 1001},
        {"query": "ok", "top_k": 21},
        {"query": "ok", "top_k": 0},
        {"query": "ok", "mode": "bm25"},
        {"query": "ok", "collection_ids": [f"c{i}" for i in range(21)]},
        {"query": "ok", "top_k": "x"},
    ):
        r = await api.c.post("/api/v1/search", headers=await api.h("a_student"), json=body)
        assert r.status_code == 422, body
    assert (await api.c.post("/api/v1/search", json={"query": "ok"})).status_code == 401


async def test_search_uses_profile_mode_and_logs_query(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    with api.services.db.session() as db:
        for c in db.scalars(select(Collection)):
            c.search_profile = {**c.search_profile, "mode": "vector"}
        db.commit()
    r = await api.search("a_student", "라운드 로빈 시간 할당량")
    assert r.status_code == 200 and r.json()["mode"] == "vector"
    with api.services.db.session() as db:
        logs = db.scalars(select(QueryLog)).all()
        assert len(logs) == 1 and logs[0].query_text is None and logs[0].hit_count == len(r.json()["hits"])
        assert logs[0].request_id == r.headers["x-request-id"]


async def test_vector_engine_down_single_mode_503(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])

    async def boom(*_a, **_k):
        raise ConnectionError("qdrant down")

    api.services.vector.search = boom
    r = await api.search("a_student", "교착 상태", mode="vector")
    assert r.status_code == 503 and r.json()["error"]["code"] == "search_unavailable"
    assert r.json()["error"]["retryable"] is True


async def test_reindex_required_warning(api, pdfs):
    up = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    s = api.services
    await s.vector.delete_document(s.vector_collection, up["document_id"])
    r = await api.c.get("/api/v1/health/ready")
    assert r.json().get("warnings") == ["reindex_required"]


def test_scope_filter_has_both_conditions():
    f = scope_filter("campus_a", ["c1", "c2"])
    keys = [c.key for c in f.must]
    assert keys == ["institution_id", "collection_id"]
