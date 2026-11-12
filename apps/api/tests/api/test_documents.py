from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.storage.models import Chunk, Document, IngestionJob

V1 = "/api/v1"


async def _doc(api, user, doc_id):
    r = await api.c.get(f"{V1}/documents/{doc_id}", headers=await api.h(user))
    assert r.status_code == 200, r.text
    return r.json()


async def test_upload_ingest_ready_korean(api, pdfs):
    cols = await api.collections("a_admin")
    r = await api.upload("a_admin", cols["operating_systems"], pdfs["korean_text.pdf"])
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "queued" and body["document_id"] and body["job_id"]
    assert (await _doc(api, "a_admin", body["document_id"]))["status"] == "queued"

    assert await api.drain() == 1
    doc = await _doc(api, "a_student", body["document_id"])
    assert doc["status"] == "ready" and doc["page_count"] == 3 and doc["active_version"] == 1
    assert doc["chunk_count"] >= 3 and doc["filename"] == "korean_text.pdf"
    assert "storage_path" not in doc

    job = (await api.c.get(f"{V1}/jobs/{body['job_id']}", headers=await api.h("a_student"))).json()
    assert job["status"] == "succeeded" and job["stage"] == "activating" and job["attempts"] == 1

    listed = await api.c.get(
        f"{V1}/collections/{cols['operating_systems']}/documents?status=ready",
        headers=await api.h("a_student"),
    )
    assert [d["id"] for d in listed.json()["items"]] == [body["document_id"]]
    cl = await api.c.get(f"{V1}/collections", headers=await api.h("a_admin"))
    item = next(c for c in cl.json()["items"] if c["slug"] == "operating_systems")
    assert item["ready_count"] == 1 and item["version"] == 2


async def test_blank_pages_ready_without_blank_chunks(api, pdfs):
    cols = await api.collections("a_admin")
    r = await api.upload("a_admin", cols["ai_basics"], pdfs["blank_pages.pdf"])
    await api.drain()
    doc = await _doc(api, "a_admin", r.json()["document_id"])
    assert doc["status"] == "ready" and doc["page_count"] == 4
    with api.services.db.session() as s:
        pages = s.scalars(select(Chunk.page_number).where(Chunk.document_id == doc["id"])).all()
    assert sorted(set(pages)) == [1, 3]


async def test_image_only_pdf_fails_unsupported_scan(api, pdfs):
    cols = await api.collections("a_admin")
    r = await api.upload("a_admin", cols["ai_basics"], pdfs["image_only.pdf"])
    await api.drain()
    doc = await _doc(api, "a_admin", r.json()["document_id"])
    assert doc["status"] == "failed" and doc["error_code"] == "unsupported_scan"
    job = (await api.c.get(f"{V1}/jobs/{r.json()['job_id']}", headers=await api.h("a_admin"))).json()
    assert job["status"] == "failed" and job["error_code"] == "unsupported_scan" and job["attempts"] == 1


async def test_too_many_pages_fails(api, pdfs):
    cols = await api.collections("a_admin")
    r = await api.upload("a_admin", cols["ai_basics"], pdfs["many_pages.pdf"])
    await api.drain()
    doc = await _doc(api, "a_admin", r.json()["document_id"])
    assert doc["status"] == "failed" and doc["error_code"] == "too_many_pages"


async def test_file_too_large_413(api, tmp_path: Path):
    cols = await api.collections("a_admin")
    big = tmp_path / "big.pdf"
    with big.open("wb") as f:
        f.write(b"%PDF-1.7\n")
        f.write(b"0" * (25 * 1024 * 1024))
    r = await api.upload("a_admin", cols["ai_basics"], big)
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"
    assert list((api.services.files.tmp).iterdir()) == []


async def test_text_file_415(api, tmp_path: Path):
    cols = await api.collections("a_admin")
    txt = tmp_path / "notes.txt"
    txt.write_text("hello")
    r = await api.upload("a_admin", cols["ai_basics"], txt)
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_media_type"
    fake = tmp_path / "fake.pdf"
    fake.write_text("not a pdf at all")
    r = await api.upload("a_admin", cols["ai_basics"], fake)
    assert r.status_code == 415


async def test_duplicate_409_and_other_collection_ok(api, pdfs):
    cols = await api.collections("a_admin")
    assert (await api.upload("a_admin", cols["ai_basics"], pdfs["korean_text.pdf"])).status_code == 202
    r = await api.upload("a_admin", cols["ai_basics"], pdfs["korean_text.pdf"], name="renamed.pdf")
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_document"
    assert (
        await api.upload("a_admin", cols["operating_systems"], pdfs["korean_text.pdf"])
    ).status_code == 202


async def test_idempotency_key_replay_200_same_body(api, pdfs):
    cols = await api.collections("a_admin")
    first = await api.upload("a_admin", cols["ai_basics"], pdfs["blank_pages.pdf"], key="k-123")
    again = await api.upload("a_admin", cols["ai_basics"], pdfs["blank_pages.pdf"], key="k-123")
    assert first.status_code == 202 and again.status_code == 200
    assert first.json() == again.json()
    with api.services.db.session() as s:
        assert len(s.scalars(select(Document)).all()) == 1


async def test_upload_permissions(api, pdfs):
    a = await api.collections("a_admin")
    r = await api.upload("a_student", a["ai_basics"], pdfs["korean_text.pdf"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_role"
    r = await api.c.post(f"{V1}/collections/{a['ai_basics']}/documents", files={"file": ("x.pdf", b"%PDF-")})
    assert r.status_code == 401


async def test_other_institution_404_everywhere(api, pdfs):
    a = await api.collections("a_admin")
    up = (await api.upload("a_admin", a["ta_only"], pdfs["korean_text.pdf"])).json()
    await api.drain()
    hb = await api.h("b_student")
    hs = await api.h("a_student")
    for headers in (hb, hs):  # 타 기관, 같은 기관이지만 역할 불허
        r = await api.c.get(f"{V1}/documents/{up['document_id']}", headers=headers)
        assert r.status_code == 404 and r.json()["error"]["code"] == "document_not_found"
        r = await api.c.get(f"{V1}/jobs/{up['job_id']}", headers=headers)
        assert r.status_code == 404 and r.json()["error"]["code"] == "job_not_found"
        r = await api.c.get(f"{V1}/collections/{a['ta_only']}/documents", headers=headers)
        assert r.status_code == 404 and r.json()["error"]["code"] == "collection_not_found"
    r = await api.c.get(f"{V1}/documents/not-a-uuid", headers=hb)
    assert r.status_code == 404


async def test_restart_recovery_requeues_processing(api, pdfs):
    a = await api.collections("a_admin")
    up = (await api.upload("a_admin", a["ai_basics"], pdfs["korean_text.pdf"])).json()
    runner = api.services.runner
    # 워커가 작업을 잡은 직후 프로세스가 죽은 상황을 만든다
    assert runner._claim() == up["job_id"]
    with api.services.db.session() as s:
        assert s.get(IngestionJob, up["job_id"]).status == "processing"
    assert runner.recover() == 1
    with api.services.db.session() as s:
        job = s.get(IngestionJob, up["job_id"])
        assert job.status == "queued" and job.attempts == 1
        assert s.get(Document, up["document_id"]).status == "queued"
    await api.drain()
    doc = await _doc(api, "a_admin", up["document_id"])
    assert doc["status"] == "ready"
    with api.services.db.session() as s:
        assert s.get(IngestionJob, up["job_id"]).attempts == 2


async def test_unexpected_error_retried_then_failed(api, pdfs, monkeypatch):
    """재시도 가능한 단계 오류는 max_attempts 까지 다시 돌고, 그 뒤 failed."""
    import app.documents.ingest as ingest

    a = await api.collections("a_admin")
    up = (await api.upload("a_admin", a["ai_basics"], pdfs["korean_text.pdf"])).json()

    def boom(*_a, **_k):
        raise RuntimeError("activation exploded")

    monkeypatch.setattr(ingest, "_activate", boom)
    await api.drain()
    doc = await _doc(api, "a_admin", up["document_id"])
    assert doc["status"] == "failed" and doc["error_code"] == "activate_failed"
    with api.services.db.session() as s:
        assert s.get(IngestionJob, up["job_id"]).attempts == 3
        assert s.scalars(select(Chunk).where(Chunk.document_id == up["document_id"])).all() == []
