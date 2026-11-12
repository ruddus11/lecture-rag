from __future__ import annotations

import pytest

from tests.fakes import FakeKeyword

Q = "교착 상태의 네 가지 필요 조건"


async def test_three_modes_200_and_hybrid_uses_both(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    res = {}
    for mode in ("keyword", "vector", "hybrid"):
        r = await api.search("a_student", Q, mode=mode)
        assert r.status_code == 200, r.text
        res[mode] = r.json()
        assert res[mode]["hits"][0]["page_number"] == 3
    assert res["keyword"]["modes_used"] == ["keyword"] and res["vector"]["modes_used"] == ["vector"]
    h = res["hybrid"]
    assert h["modes_used"] == ["keyword", "vector"] and h["degraded"] is False
    assert h["keyword_analyzer"] == "korean"
    top = h["hits"][0]
    assert top["keyword_rank"] == 1 and top["vector_rank"] == 1
    assert top["score"] == pytest.approx(2 / 61, abs=1e-6)
    for key in ("keyword", "vector", "embed_query", "fusion", "ledger_check", "total"):
        assert key in h["timings_ms"]
    assert res["keyword"]["hits"][0]["vector_rank"] is None


async def test_keyword_down_hybrid_degraded_keyword_503(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    api.services.keyword.ok = False
    r = await api.search("a_student", Q, mode="hybrid")
    assert r.status_code == 200
    assert r.json()["degraded"] is True and r.json()["modes_used"] == ["vector"] and r.json()["hits"]
    r = await api.search("a_student", Q, mode="keyword")
    assert r.status_code == 503 and r.json()["error"]["code"] == "search_unavailable"
    api.services.keyword.ok = True  # 재기동 후 정상
    r = await api.search("a_student", Q, mode="hybrid")
    assert r.json()["degraded"] is False and r.json()["modes_used"] == ["keyword", "vector"]


async def test_both_down_503(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    api.services.keyword.ok = False

    async def boom(*_a, **_k):
        raise TimeoutError

    api.services.vector.search = boom
    r = await api.search("a_student", Q, mode="hybrid")
    assert r.status_code == 503 and r.json()["error"]["retryable"] is True


async def test_keyword_engine_timeout_counts_as_failure(api, pdfs, monkeypatch):
    import asyncio

    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    original = api.services.keyword.search

    async def slow(*a, **k):
        await asyncio.sleep(0.5)
        return await original(*a, **k)

    api.services.keyword.search = slow
    monkeypatch.setattr(api.services.settings, "search_engine_timeout_ms", 100)
    r = await api.search("a_student", Q, mode="hybrid")
    assert r.status_code == 200 and r.json()["degraded"] is True and r.json()["modes_used"] == ["vector"]


async def test_keyword_filter_branch_and_isolation(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    kw: FakeKeyword = api.services.keyword
    b_net = (await api.collections("b_student"))["networks"]
    assert await kw.search(Q, "campus_b", [b_net], 10) == []
    kw.filters_enabled = False
    try:
        assert await kw.search(Q, "campus_b", [b_net], 10)
        r = await api.search("b_student", Q, mode="hybrid")
        assert r.status_code == 200 and r.json()["hits"] == []
    finally:
        kw.filters_enabled = True


async def test_failed_ingest_cleans_both_engines(api, pdfs, monkeypatch):
    import app.documents.ingest as ingest

    up = await api.ingest("a_admin", "ai_basics", pdfs["blank_pages.pdf"])
    assert await api.services.keyword.count_document(up["document_id"], 1) == 2

    def boom(*_a, **_k):
        raise RuntimeError("activation exploded")

    monkeypatch.setattr(ingest, "_activate", boom)
    up2 = await api.ingest("a_admin", "ai_basics", pdfs["korean_text.pdf"])
    s = api.services
    assert await s.keyword.count_document(up2["document_id"]) == 0
    assert await s.vector.count_document(s.vector_collection, up2["document_id"]) == 0
