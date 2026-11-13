"""M10 캐시 격리·갱신 (설계서 10.1, 16장 M10 완료 기준). 테스트 기본 설정은 임베딩 3600s·검색 300s 캐시 on."""

from __future__ import annotations

import pytest

from app.core import cache as cache_mod
from app.retrieval import service as service_mod

Q = "교착 상태의 네 가지 필요 조건"


def _docs(body: dict) -> set[str]:
    return {h["document_id"] for h in body["hits"]}


async def test_second_identical_search_hits_cache_with_same_hits(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    first = (await api.search("a_student", Q, mode="hybrid")).json()
    calls = api.services.embedder.calls
    second = (await api.search("a_student", f"  {Q} ", mode="hybrid")).json()  # 정규화 후 같은 키
    assert (first["cache_status"], second["cache_status"]) == ("miss", "hit")
    assert second["hits"] == first["hits"] and second["modes_used"] == ["keyword", "vector"]
    assert api.services.embedder.calls == calls  # 적중이면 임베딩도 다시 하지 않는다
    other_mode = (await api.search("a_student", Q, mode="vector")).json()
    assert other_mode["cache_status"] == "embed_hit"  # 모드가 다르면 검색 키는 다르고 임베딩만 재사용


@pytest.mark.parametrize(
    "settings_overrides", [{"cache_embed_ttl_seconds": 0, "cache_retrieval_ttl_seconds": 0}]
)
async def test_ttl_zero_disables_both_caches(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    for _ in range(2):
        r = (await api.search("a_student", Q, mode="hybrid")).json()
        assert r["cache_status"] == "off"
    assert not api.services.cache.retrieval and not api.services.cache.embeddings


async def test_cached_result_not_visible_to_other_role_or_institution(api, pdfs):
    await api.ingest("a_admin", "ta_only", pdfs["korean_text.pdf"])
    admin = (await api.search("a_admin", Q, mode="hybrid")).json()
    assert admin["hits"] and admin["cache_status"] == "miss"
    student = (await api.search("a_student", Q, mode="hybrid")).json()
    assert student["cache_status"] != "hit" and student["hits"] == []  # ta_only 는 admin 전용
    b = (await api.search("b_student", Q, mode="hybrid")).json()
    assert b["cache_status"] != "hit" and b["hits"] == []


async def test_key_collision_still_filtered_by_ledger(api, pdfs, monkeypatch):
    """키가 겹치더라도(가상의 버그) 적중 결과는 원장 대조에서 요청자 scope 밖 청크가 빠진다."""
    monkeypatch.setattr(service_mod, "retrieval_key", lambda *a, **k: "same-key")
    await api.ingest("a_admin", "ta_only", pdfs["korean_text.pdf"])
    assert (await api.search("a_admin", Q, mode="hybrid")).json()["hits"]
    for user in ("a_student", "b_student"):
        r = (await api.search(user, Q, mode="hybrid")).json()
        assert r["cache_status"] == "hit" and r["hits"] == []


async def test_deleted_document_absent_from_cached_hit_within_ttl(api, pdfs, monkeypatch):
    doc = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    did = doc["document_id"]
    await api.search("a_student", Q, mode="hybrid")
    assert did in _docs((await api.search("a_student", Q, mode="hybrid")).json())
    r = await api.c.delete(f"/api/v1/documents/{did}", headers=await api.h("a_admin"))
    assert r.status_code == 202, r.text
    after = (await api.search("a_student", Q, mode="hybrid")).json()
    assert after["cache_status"] != "hit" and did not in _docs(after)  # 삭제가 collection.version 을 올린다


async def test_deleted_document_filtered_even_if_stale_entry_is_hit(api, pdfs, monkeypatch):
    """clear() 와 버전 키가 모두 빠진 가상의 상황에서도 적중 결과의 원장 대조가 삭제 문서를 뺀다."""
    monkeypatch.setattr(service_mod, "retrieval_key", lambda *a, **k: "same-key")
    monkeypatch.setattr(type(api.services), "invalidate_caches", lambda self: None)
    doc = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    did = doc["document_id"]
    assert did in _docs((await api.search("a_student", Q, mode="hybrid")).json())
    await api.c.delete(f"/api/v1/documents/{did}", headers=await api.h("a_admin"))
    after = (await api.search("a_student", Q, mode="hybrid")).json()
    assert after["cache_status"] == "hit" and did not in _docs(after)
    answer = (await api.answer("a_student", Q, mode="hybrid")).json()
    assert did not in _docs(answer) and not answer["citations"]


async def test_delete_clears_cache(api, pdfs):
    doc = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    await api.search("a_student", Q, mode="hybrid")
    assert api.services.cache.retrieval
    await api.c.delete(f"/api/v1/documents/{doc['document_id']}", headers=await api.h("a_admin"))
    assert not api.services.cache.retrieval and not api.services.cache.embeddings
    r = (await api.search("a_student", Q, mode="hybrid")).json()
    assert r["cache_status"] != "hit" and r["hits"] == []


async def test_new_version_changes_scope_fingerprint(api, pdfs, monkeypatch):
    """활성화로 collection.version 이 오르면 clear() 없이도 이전 키가 쓰이지 않는다."""
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    await api.search("a_student", Q, mode="hybrid")
    monkeypatch.setattr(type(api.services), "invalidate_caches", lambda self: None)
    await api.ingest("a_admin", "operating_systems", pdfs["injection.pdf"])
    r = (await api.search("a_student", Q, mode="hybrid")).json()
    assert r["cache_status"] in ("miss", "embed_hit")


async def test_degraded_result_is_not_cached(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    api.services.keyword.ok = False
    r = (await api.search("a_student", Q, mode="hybrid")).json()
    assert r["degraded"] is True and not api.services.cache.retrieval
    api.services.keyword.ok = True
    r = (await api.search("a_student", Q, mode="hybrid")).json()
    assert r["degraded"] is False and r["cache_status"] != "hit"
    assert r["modes_used"] == ["keyword", "vector"]


def test_cache_store_flags():
    assert not cache_mod.CacheStore().embed_enabled
    store = cache_mod.CacheStore(1, 0)
    assert store.embed_enabled and not store.retrieval_enabled
