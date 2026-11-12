from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.container import Services
from app.core.config import Settings
from app.main import create_app


class _Embedder:
    name, model, dim = "local", "fake", 8

    def __init__(self, loaded: bool = True) -> None:
        self.loaded = loaded

    def load(self) -> None:
        pass

    def is_loaded(self) -> bool:
        return self.loaded


class _Vector:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    async def ping(self) -> bool:
        if not self.ok:
            raise ConnectionError("down")
        return True


class _Keyword:
    def __init__(self, nori: bool = True) -> None:
        self.nori = nori

    async def health(self) -> dict:
        return {"status": "green"}

    async def has_nori(self) -> bool:
        return self.nori


def _app(tmp_path: Path, **kw):
    settings = Settings(app_env="test", data_dir=tmp_path, _env_file=None)
    services = Services(
        settings=settings,
        embedder=kw.get("embedder", _Embedder()),
        vector=kw.get("vector", _Vector()),
        keyword=kw.get("keyword", _Keyword()),
    )
    return create_app(settings, services_factory=lambda s: services)


async def _get(app, path: str) -> httpx.Response:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await c.get(path)


async def test_live(tmp_path):
    r = await _get(_app(tmp_path), "/api/v1/health/live")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_ready_ok(tmp_path):
    r = await _get(_app(tmp_path), "/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["checks"] == {
        "sqlite": True,
        "qdrant": True,
        "opensearch": True,
        "nori": True,
        "embedding_model": True,
    }


@pytest.mark.parametrize(
    "kw,failed",
    [
        ({"vector": _Vector(ok=False)}, "qdrant"),
        ({"keyword": _Keyword(nori=False)}, "nori"),
        ({"embedder": _Embedder(loaded=False)}, "embedding_model"),
    ],
)
async def test_ready_degraded(tmp_path, kw, failed):
    r = await _get(_app(tmp_path, **kw), "/api/v1/health/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["checks"][failed] is False
