from sqlalchemy import select

from app.storage.models import Chunk, Collection, Document, IngestionJob


async def test_delete_blocks_immediately_then_removes_data(api, pdfs):
    up = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    did = up["document_id"]
    with api.services.db.session() as db:
        doc = db.get(Document, did)
        path = api.services.files.resolve_stored(doc.storage_path)
        cid = doc.collection_id
        version = db.get(Collection, cid).version
    r = await api.c.delete(f"/api/v1/documents/{did}", headers=await api.h("a_admin"))
    assert r.status_code == 202
    assert path.exists()  # 워커 실행 전에도 원장으로 차단되어야 한다.
    assert (
        await api.c.get(f"/api/v1/documents/{did}/file", headers=await api.h("a_student"))
    ).status_code == 404
    assert (await api.search("a_student", "교착 상태", mode="hybrid")).json()["hits"] == []
    answer = (await api.answer("a_student", "교착 상태")).json()
    assert answer["abstained"] and answer["citations"] == []
    with api.services.db.session() as db:
        assert db.get(Collection, cid).version == version + 1
    await api.drain()
    assert not path.exists()
    with api.services.db.session() as db:
        assert db.get(Document, did).status == "deleted"
        assert db.scalars(select(Chunk).where(Chunk.document_id == did)).all() == []
    assert await api.services.vector.count_document(api.services.vector_collection, did) == 0
    assert await api.services.keyword.count_document(did) == 0


async def test_retry_increments_target_and_removes_previous_version(api, pdfs):
    up = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    did = up["document_id"]
    with api.services.db.session() as db:
        db.get(Document, did).status = "failed"
        db.commit()
    url = f"/api/v1/documents/{did}/retry"
    h = await api.h("a_admin")
    assert (await api.c.post(url, headers=h, json={"expected_version": 0})).status_code == 409
    r = await api.c.post(url, headers=h, json={"expected_version": 1})
    assert r.status_code == 202
    assert (await api.c.post(url, headers=h, json={"expected_version": 1})).status_code == 409
    with api.services.db.session() as db:
        assert db.get(IngestionJob, r.json()["job_id"]).target_version == 2
    await api.drain()
    with api.services.db.session() as db:
        assert db.get(Document, did).active_version == 2
    assert await api.services.vector.count_document(api.services.vector_collection, did, 1) == 0
    assert await api.services.keyword.count_document(did, 1) == 0


async def test_isolation_five_paths_and_admin_operations(api, pdfs):
    up = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    did = up["document_id"]
    b = await api.h("b_student")
    for path in [f"documents/{did}", f"jobs/{up['job_id']}", f"documents/{did}/file"]:
        assert (await api.c.get(f"/api/v1/{path}", headers=b)).status_code == 404
    assert (await api.search("b_student", "교착 상태")).json()["hits"] == []
    assert (await api.answer("b_student", "교착 상태")).json()["citations"] == []
    assert (await api.c.delete(f"/api/v1/documents/{did}", headers=b)).status_code == 403
    assert (await api.c.delete(f"/api/v1/documents/{did}", headers=await api.h("b_admin"))).status_code == 404


async def test_delete_failure_retry_and_recovery(api, pdfs, monkeypatch):
    up = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    did = up["document_id"]
    url = f"/api/v1/documents/{did}"
    h = await api.h("a_admin")
    original = api.services.keyword.delete_document

    async def unavailable(*args, **kwargs):
        raise ConnectionError("engine down")

    monkeypatch.setattr(api.services.keyword, "delete_document", unavailable)
    r = await api.c.delete(url, headers=h)
    assert r.status_code == 202
    await api.drain()
    with api.services.db.session() as db:
        assert db.get(Document, did).status == "deleting"
        assert db.get(IngestionJob, r.json()["job_id"]).status == "failed"
    monkeypatch.setattr(api.services.keyword, "delete_document", original)
    r = await api.c.post(url + "/retry", headers=h, json={"expected_version": 1})
    assert r.status_code == 202
    with api.services.db.session() as db:
        job = db.get(IngestionJob, r.json()["job_id"])
        assert job.kind == "delete"
        job.status = "processing"
        db.commit()
    assert api.services.runner.recover() == 1
    await api.drain()
    with api.services.db.session() as db:
        assert db.get(Document, did).status == "deleted"


async def test_delete_queued_document_never_resurrects(api, pdfs, monkeypatch):
    cols = await api.collections("a_admin")
    up = (await api.upload("a_admin", cols["operating_systems"], pdfs["korean_text.pdf"])).json()
    did = up["document_id"]
    await api.c.delete(f"/api/v1/documents/{did}", headers=await api.h("a_admin"))
    original = api.services.doc_embedder.embed_documents

    def assert_still_deleting(texts):
        with api.services.db.session() as db:
            assert db.get(Document, did).status == "deleting"
        return original(texts)

    monkeypatch.setattr(api.services.doc_embedder, "embed_documents", assert_still_deleting)
    # 한 작업만 실행해도 수집 작업이 문서 상태를 processing/failed로 바꾸면 안 된다.
    await api.services.runner.run_once()
    with api.services.db.session() as db:
        assert db.get(Document, did).status in ("deleting", "deleted")
    await api.drain()


async def test_delete_during_generation_drops_answer_and_evidence(api, pdfs, monkeypatch):
    up = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    did = up["document_id"]
    original = api.services.answers.provider.generate

    async def delete_before_return(question, evidences):
        response = await original(question, evidences)
        r = await api.c.delete(f"/api/v1/documents/{did}", headers=await api.h("a_admin"))
        assert r.status_code == 202
        return response

    monkeypatch.setattr(api.services.answers.provider, "generate", delete_before_return)
    r = await api.answer("a_student", "교착 상태")
    body = r.json()
    assert body["abstained"] and body["answer"] == ""
    assert body["citations"] == [] and body["hits"] == []


async def test_delete_contract_and_repeated_requests(api, pdfs):
    up = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    url = f"/api/v1/documents/{up['document_id']}"
    h = await api.h("a_admin")
    r = await api.c.delete(url, headers=h)
    assert r.json()["status"] == "deleting"
    assert (await api.c.delete(url, headers=h)).status_code == 409
    await api.drain()
    assert (await api.c.delete(url, headers=h)).status_code == 409
    assert (await api.c.delete(url, headers=await api.h("b_admin"))).status_code == 404
