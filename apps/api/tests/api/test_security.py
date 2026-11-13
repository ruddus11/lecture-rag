"""M11: CORS, 본문 상한, request id, 파일 경로 경계."""

import pytest


async def test_cors_allowlist(api):
    for origin, status in [("http://localhost:5173", 200), ("https://evil.invalid", 400)]:
        r = await api.c.options(
            "/api/v1/search",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert r.status_code == status
        assert r.headers.get("access-control-allow-origin") == (origin if status == 200 else None)


@pytest.mark.parametrize("chunked", [False, True])
async def test_request_body_limit(api, chunked):
    body = b"x" * (21 * 1024 * 1024 + 1)

    async def chunks():
        for pos in range(0, len(body), 1024 * 1024):
            yield body[pos : pos + 1024 * 1024]

    r = await api.c.post("/api/v1/auth/login", content=chunks() if chunked else body)
    assert r.status_code == 413
    assert r.json()["error"]["request_id"] == r.headers["x-request-id"]


async def test_request_id_rejects_invalid_and_preserves_valid(api):
    good = "acceptance-m11"
    r = await api.c.get("/api/v1/health/live", headers={"X-Request-Id": good})
    assert r.headers["x-request-id"] == good
    r = await api.c.get("/api/v1/health/live", headers={"X-Request-Id": "invalid id"})
    assert r.headers["x-request-id"] != "invalid id"


def test_file_path_traversal_and_symlink(api, tmp_path):
    store = api.services.files
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"private")
    with pytest.raises(ValueError):
        store.resolve_stored(str(store.data_dir / ".." / "outside.pdf"))
    link = store.root / "escape.pdf"
    link.symlink_to(outside)
    with pytest.raises(ValueError):
        store.resolve_stored(str(link))
