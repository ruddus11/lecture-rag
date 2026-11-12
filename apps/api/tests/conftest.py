from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.container import Services
from app.core.config import Settings
from app.core.ratelimit import RateLimiter
from app.main import create_app
from app.storage.db import Database
from tests.fakes import FakeEmbedder, FakeKeyword, FakeVector

REPO = Path(__file__).resolve().parents[3]
DEMO_PASSWORDS = {
    "a_admin": "admin-a-demo-2026",
    "a_student": "student-a-demo-2026",
    "b_student": "student-b-demo-2026",
}
TEST_SECRET = "test-secret-0123456789-abcdefghijklmnop"


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    base: dict[str, Any] = dict(
        app_env="test",
        data_dir=tmp_path / "data",
        institutions_file=REPO / "config" / "institutions.example.yaml",
        users_file=REPO / "config" / "users.example.yaml",
        auth_secret=TEST_SECRET,
        rate_limit_enabled=False,
        log_level="WARNING",
        _env_file=None,
    )
    base.update(overrides)
    return Settings(**base)


def make_services_factory(**parts: Any) -> Callable[[Settings], Services]:
    def factory(settings: Settings) -> Services:
        return Services(
            settings=settings,
            db=Database(settings.db_url),
            embedder=parts.get("embedder") or FakeEmbedder(),
            vector=parts.get("vector") or FakeVector(),
            keyword=parts.get("keyword") or FakeKeyword(),
            ratelimiter=RateLimiter(settings),
        )

    return factory


class Api:
    """테스트용 클라이언트 묶음. 로그인 토큰을 캐시한다."""

    def __init__(self, app: FastAPI, client: httpx.AsyncClient) -> None:
        self.app = app
        self.c = client
        self._tokens: dict[str, str] = {}

    @property
    def services(self) -> Services:
        return self.app.state.services  # type: ignore[no-any-return]

    async def token(self, username: str) -> str:
        if username not in self._tokens:
            r = await self.c.post(
                "/api/v1/auth/login", json={"username": username, "password": DEMO_PASSWORDS[username]}
            )
            assert r.status_code == 200, r.text
            self._tokens[username] = r.json()["access_token"]
        return self._tokens[username]

    async def h(self, username: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self.token(username)}"}

    async def collections(self, username: str) -> dict[str, str]:
        r = await self.c.get("/api/v1/collections", headers=await self.h(username))
        assert r.status_code == 200, r.text
        return {c["slug"]: c["id"] for c in r.json()["items"]}

    async def upload(
        self, username: str, collection_id: str, path: Path, key: str | None = None, name: str | None = None
    ) -> httpx.Response:
        headers = await self.h(username)
        if key:
            headers["Idempotency-Key"] = key
        return await self.c.post(
            f"/api/v1/collections/{collection_id}/documents",
            headers=headers,
            files={"file": (name or path.name, path.read_bytes(), "application/pdf")},
        )

    async def drain(self) -> int:
        assert self.services.runner is not None
        return await self.services.runner.drain()


@pytest.fixture(scope="session")
def pdfs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    from tests.fixtures.make_pdfs import make_all

    return make_all(tmp_path_factory.mktemp("pdfs"))


@pytest.fixture
def settings_overrides() -> dict[str, Any]:
    return {}


@pytest.fixture
def service_parts() -> dict[str, Any]:
    return {}


@pytest.fixture
async def api(
    tmp_path: Path, settings_overrides: dict[str, Any], service_parts: dict[str, Any]
) -> AsyncIterator[Api]:
    settings = make_settings(tmp_path, **settings_overrides)
    app = create_app(settings, services_factory=make_services_factory(**service_parts), start_worker=False)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield Api(app, client)
