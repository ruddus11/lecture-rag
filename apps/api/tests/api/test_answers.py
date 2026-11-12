from __future__ import annotations

from sqlalchemy import select

from app.generation.base import ProviderError
from app.storage.models import QueryLog

Q = "교착 상태의 네 가지 필요 조건은?"


async def test_answer_with_valid_citation_in_hits(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    r = await api.answer("a_student", Q)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["abstained"] is False and b["abstain_reason"] is None and b["answer"]
    assert b["provider"] == {"name": "fake", "model": "fake"} and b["mode"] == "hybrid"
    hit_ids = {h["chunk_id"] for h in b["hits"]}
    assert b["citations"] and all(c["chunk_id"] in hit_ids for c in b["citations"])
    assert b["citations"][0]["page_number"] == 3 and b["citations"][0]["document_title"] == "korean_text.pdf"
    assert len(b["hits"]) <= 5  # context_k
    for k in ("retrieval", "generation", "verify", "total"):
        assert k in b["timings_ms"]
    with api.services.db.session() as db:
        log = db.scalars(select(QueryLog)).one()
        assert log.provider == "fake" and log.abstained == 0 and log.query_text is None


async def test_invalid_id_retried_once_then_abstain(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    fake = api.services.answer_provider
    before = fake.calls
    b = (await api.answer("a_student", Q + " [[bad_id]]")).json()
    assert b["abstained"] is True and b["abstain_reason"] == "invalid_citations"
    assert b["answer"] == "" and b["citations"] == [] and b["hits"]
    assert fake.calls - before == 2  # ANSWER_MAX_ATTEMPTS=2


async def test_quote_mismatch_abstain(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    b = (await api.answer("a_student", Q + " [[bad_quote]]")).json()
    assert b["abstained"] is True and b["abstain_reason"] == "invalid_citations"


async def test_zero_hits_no_llm_call(api, pdfs):
    fake = api.services.answer_provider
    before = fake.calls
    b = (await api.answer("b_student", Q)).json()  # campus_b 에는 문서가 없다
    assert b["abstained"] is True and b["abstain_reason"] == "no_evidence" and b["hits"] == []
    assert fake.calls == before


async def test_no_evidence_marker_and_refusal(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    b = (await api.answer("a_student", Q + " [[no_evidence]]")).json()
    assert b["abstained"] and b["abstain_reason"] == "insufficient_evidence" and b["hits"]
    b = (await api.answer("a_student", Q + " [[refuse]]")).json()
    assert b["abstained"] and b["abstain_reason"] == "provider_refused"


async def test_provider_unavailable_degraded_with_hits(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    r = await api.answer("a_student", Q + " [[error]]")
    b = r.json()
    assert r.status_code == 200 and b["abstained"] and b["abstain_reason"] == "provider_unavailable"
    assert b["degraded"] is True and b["hits"] and b["answer"] == ""


async def test_provider_rate_limit_429_and_other_500(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    fake = api.services.answer_provider

    async def rl(*_a, **_k):
        raise ProviderError(429, "provider_rate_limited", "rl")

    fake.generate = rl
    r = await api.answer("a_student", Q)
    assert r.status_code == 429 and r.json()["error"]["code"] == "provider_rate_limited"
    assert r.headers.get("retry-after") and r.json()["error"]["retryable"] is True

    async def bad(*_a, **_k):
        raise ProviderError(500, "provider_error", "bad request")

    fake.generate = bad
    r = await api.answer("a_student", Q)
    assert r.status_code == 500 and r.json()["error"]["code"] == "provider_error"


async def test_injection_pdf_not_followed(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["injection.pdf"])
    b = (await api.answer("a_student", "LRU 페이지 교체 알고리즘은 무엇을 교체하나?")).json()
    assert b["abstained"] is False
    assert "LRU" in b["answer"] and "시스템 프롬프트" not in b["answer"]
    assert "근거만" not in b["answer"] and all(
        c["chunk_id"] in {h["chunk_id"] for h in b["hits"]} for c in b["citations"]
    )


async def test_answers_validation_and_auth(api):
    assert (await api.c.post("/api/v1/answers", json={"query": "x"})).status_code == 401
    r = await api.c.post("/api/v1/answers", headers=await api.h("a_student"), json={"query": ""})
    assert r.status_code == 422
