"""integration: 실제 qdrant·opensearch 가 필요하다. `pytest -m integration`.

IT_QDRANT_URL / IT_OPENSEARCH_URL 환경변수(기본 127.0.0.1)로 접속한다.
각 테스트는 고유 이름의 컬렉션·인덱스를 쓰고 지운다.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.retrieval.vector import QdrantStore

QDRANT_URL = os.environ.get("IT_QDRANT_URL", "http://127.0.0.1:6333")
OPENSEARCH_URL = os.environ.get("IT_OPENSEARCH_URL", "http://127.0.0.1:9200")


@pytest.fixture
async def qdrant() -> AsyncIterator[tuple[QdrantStore, str]]:
    store = QdrantStore(QDRANT_URL, 5000)
    name = f"it_{uuid.uuid4().hex[:8]}__8"
    yield store, name
    await store.client.delete_collection(name)
    await store.close()


@pytest.fixture
async def it_api(tmp_path) -> AsyncIterator[Any]:
    """실제 Qdrant·OpenSearch 에 붙은 앱. 임베딩만 fake(빠름). 테스트 전용 인덱스·컬렉션을 쓰고 지운다."""
    import httpx

    from app.main import create_app
    from app.retrieval.keyword import OpenSearchStore
    from tests.conftest import Api, make_services_factory, make_settings
    from tests.fakes import FakeEmbedder

    tag = uuid.uuid4().hex[:8]
    vector = QdrantStore(QDRANT_URL, 5000)
    keyword = OpenSearchStore(OPENSEARCH_URL, 5000, "korean")
    keyword.index = f"it_chunks_{tag}"
    embedder = FakeEmbedder()
    embedder.model = f"it-{tag}"
    settings = make_settings(tmp_path, search_engine_timeout_ms=5000)
    factory = make_services_factory(embedder=embedder, vector=vector, keyword=keyword)
    app = create_app(settings, services_factory=factory, start_worker=False)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            api = Api(app, client)
            try:
                yield api
            finally:
                s = api.services
                await vector.client.delete_collection(s.vector_collection)
                await keyword.client.indices.delete(
                    index=keyword.index, params={"ignore_unavailable": "true"}
                )
