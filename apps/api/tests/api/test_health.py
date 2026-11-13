from __future__ import annotations

import pytest

from tests.fakes import FakeEmbedder, FakeKeyword, FakeVector


async def test_live(api):
    r = await api.c.get("/api/v1/health/live")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert r.headers["x-request-id"]


async def test_ready_ok(api):
    r = await api.c.get("/api/v1/health/ready")
    assert r.status_code == 200, r.text
    checks = r.json()["checks"]
    assert checks["sqlite"] and checks["qdrant"] and checks["opensearch"] and checks["nori"]
    assert checks["embedding_model"] is True
    assert {"institution_id", "collection_id", "document_id"} <= set(checks["opensearch_keyword_fields"])


@pytest.mark.parametrize(
    "service_parts,failed",
    [
        ({"vector": FakeVector(ok=False)}, "qdrant"),
        ({"keyword": FakeKeyword(ok=False)}, "opensearch"),
        ({"keyword": FakeKeyword(nori=False)}, "nori"),
        ({"embedder": FakeEmbedder(loaded=False)}, "embedding_model"),
    ],
)
async def test_ready_degraded(api, failed):
    if failed == "embedding_model":
        api.services.embedder.loaded = False  # lifespan 의 백그라운드 load 를 되돌린다
    r = await api.c.get("/api/v1/health/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["checks"][failed] is False


@pytest.mark.parametrize(
    "settings_overrides,service_parts",
    [({"keyword_analyzer": "standard"}, {"keyword": FakeKeyword(nori=False)})],
)
async def test_ready_standard_analyzer_skips_nori(api):
    r = await api.c.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["checks"]["nori"].startswith("skipped")


async def test_meta_requires_login(api):
    assert (await api.c.get("/api/v1/meta")).status_code == 401
    r = await api.c.get("/api/v1/meta", headers=await api.h("a_student"))
    assert r.status_code == 200
    body = r.json()
    assert body["chunker_version"] == "v1" and body["parser_version"] == "pymupdf-v1"
    assert body["embedding"]["model"] == "fake-embed"


async def test_request_id_passthrough(api):
    r = await api.c.get("/api/v1/health/live", headers={"X-Request-Id": "client-req-12345"})
    assert r.headers["x-request-id"] == "client-req-12345"
    r = await api.c.get("/api/v1/health/live", headers={"X-Request-Id": "bad id with spaces"})
    assert r.headers["x-request-id"] != "bad id with spaces" and len(r.headers["x-request-id"]) == 26
