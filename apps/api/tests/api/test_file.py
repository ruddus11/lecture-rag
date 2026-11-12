from __future__ import annotations

from urllib.parse import quote

from app.storage.models import Document


async def test_file_full_and_range(api, pdfs):
    up = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    raw = pdfs["korean_text.pdf"].read_bytes()
    url = f"/api/v1/documents/{up['document_id']}/file"
    h = await api.h("a_student")
    r = await api.c.get(url, headers=h)
    assert r.status_code == 200 and r.content == raw
    assert r.headers["content-type"] == "application/pdf" and r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-disposition"] == "inline; filename*=UTF-8''korean_text.pdf"
    r = await api.c.get(url, headers={**h, "Range": "bytes=0-99"})
    assert r.status_code == 206 and r.content == raw[:100]
    assert r.headers["content-range"] == f"bytes 0-99/{len(raw)}"
    r = await api.c.get(url, headers={**h, "Range": "bytes=-10"})
    assert r.status_code == 206 and r.content == raw[-10:]
    r = await api.c.get(url, headers={**h, "Range": f"bytes={len(raw)}-"})
    assert r.status_code == 416


async def test_file_korean_filename_rfc5987(api, pdfs):
    a = await api.collections("a_admin")
    up = (
        await api.upload("a_admin", a["ai_basics"], pdfs["blank_pages.pdf"], name="운영체제 3주차.pdf")
    ).json()
    await api.drain()
    r = await api.c.get(f"/api/v1/documents/{up['document_id']}/file", headers=await api.h("a_admin"))
    assert (
        r.headers["content-disposition"] == f"inline; filename*=UTF-8''{quote('운영체제 3주차.pdf', safe='')}"
    )


async def test_file_scope_and_status(api, pdfs):
    up = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    url = f"/api/v1/documents/{up['document_id']}/file"
    assert (await api.c.get(url, headers=await api.h("b_student"))).status_code == 404
    assert (await api.c.get(url)).status_code == 401
    with api.services.db.session() as db:
        db.get(Document, up["document_id"]).status = "failed"
        db.commit()
    r = await api.c.get(url, headers=await api.h("a_admin"))
    assert r.status_code == 404 and r.json()["error"]["code"] == "document_not_found"


async def test_storage_path_outside_data_dir_rejected(api, pdfs):
    up = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    with api.services.db.session() as db:
        db.get(Document, up["document_id"]).storage_path = "/etc/passwd"
        db.commit()
    r = await api.c.get(f"/api/v1/documents/{up['document_id']}/file", headers=await api.h("a_admin"))
    assert r.status_code == 404
