"""integration: 실제 qdrant·opensearch 가 필요하다. `pytest -m integration`.

IT_QDRANT_URL / IT_OPENSEARCH_URL 환경변수(기본 127.0.0.1)로 접속한다.
각 테스트는 고유 이름의 컬렉션·인덱스를 쓰고 지운다.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

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
