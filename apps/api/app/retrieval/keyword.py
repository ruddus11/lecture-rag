"""OpenSearch 어댑터 (설계서 4.3, 6.2). 앱 전역 AsyncOpenSearch 1개.

- 인덱스 설정·매핑은 infra/opensearch/index-chunks.json. 없으면 생성한다.
- KEYWORD_ANALYZER=standard 이면 Nori 없이 standard analyzer 로 만든 별도 인덱스(chunks_v1_standard)를 쓴다.
- 검색은 multi_match(text^1.0, text.std^0.3, best_fields, or) + bool.filter(institution_id, collection_id).
"""

from __future__ import annotations

import copy
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from opensearchpy import AsyncOpenSearch

from app.core.config import OPENSEARCH_INDEX
from app.retrieval.types import Candidate, ChunkDoc

log = logging.getLogger(__name__)

BULK_BATCH = 200
_HERE = Path(__file__).resolve()
_CANDIDATES = [
    _HERE.parents[2] / "infra" / "opensearch" / "index-chunks.json",  # 컨테이너 /app/infra/...
    _HERE.parents[4] / "infra" / "opensearch" / "index-chunks.json",  # 저장소 루트
]


@lru_cache(maxsize=1)
def index_body_korean() -> dict[str, Any]:
    for p in _CANDIDATES:
        if p.exists():
            return dict(json.loads(p.read_text(encoding="utf-8")))
    raise FileNotFoundError("infra/opensearch/index-chunks.json")


def index_body(analyzer: str) -> dict[str, Any]:
    body = copy.deepcopy(index_body_korean())
    if analyzer == "standard":
        body["settings"].pop("analysis", None)
        text = body["mappings"]["properties"]["text"]
        text["analyzer"] = text["search_analyzer"] = "standard"
    return body


def index_name(analyzer: str) -> str:
    return OPENSEARCH_INDEX if analyzer == "korean" else f"{OPENSEARCH_INDEX}_standard"


def _doc_filter(document_id: str, version: int | None, below_version: int | None) -> dict[str, Any]:
    flt: list[dict[str, Any]] = [{"term": {"document_id": document_id}}]
    if version is not None:
        flt.append({"term": {"document_version": version}})
    if below_version is not None:
        flt.append({"range": {"document_version": {"lt": below_version}}})
    return {"bool": {"filter": flt}}


class OpenSearchStore:
    def __init__(self, url: str, timeout_ms: int = 2000, analyzer: str = "korean") -> None:
        self.url = url
        self.timeout_s = max(1.0, timeout_ms / 1000)
        self.analyzer = analyzer
        self.index = index_name(analyzer)
        self.client = AsyncOpenSearch(hosts=[url], timeout=self.timeout_s, max_retries=0)
        self.filters_enabled = True  # 테스트 전용 (vector 와 같은 의미)
        self._ensured = False

    async def health(self) -> dict[str, Any]:
        health = await self.client.cluster.health()
        return {"status": health.get("status")}

    async def has_nori(self) -> bool:
        plugins = await self.client.cat.plugins(format="json")
        return any(p.get("component") == "analysis-nori" for p in plugins)

    async def ensure_index(self) -> None:
        if self._ensured:
            return
        if not await self.client.indices.exists(index=self.index):
            try:
                await self.client.indices.create(index=self.index, body=index_body(self.analyzer))
                log.info(
                    "opensearch_index_created",
                    extra={"event": "opensearch_index_created", "index": self.index},
                )
            except Exception:
                if not await self.client.indices.exists(index=self.index):
                    raise
        self._ensured = True

    async def bulk_index(self, docs: list[ChunkDoc]) -> None:
        for i in range(0, len(docs), BULK_BATCH):
            lines: list[dict[str, Any]] = []
            for d in docs[i : i + BULK_BATCH]:
                lines.append({"index": {"_index": self.index, "_id": d.chunk_id}})
                lines.append(d.payload())
            resp = await self.client.bulk(body=lines, params={"refresh": "wait_for", "request_timeout": 30})
            if resp.get("errors"):
                bad = [it for it in resp.get("items", []) if it.get("index", {}).get("error")]
                raise RuntimeError(f"bulk errors: {json.dumps(bad[:2], ensure_ascii=False)[:300]}")

    async def count_document(self, document_id: str, version: int | None = None) -> int:
        if not await self.client.indices.exists(index=self.index):
            return 0
        resp = await self.client.count(
            index=self.index, body={"query": _doc_filter(document_id, version, None)}
        )
        return int(resp["count"])

    async def delete_document(
        self, document_id: str, version: int | None = None, below_version: int | None = None
    ) -> None:
        if not await self.client.indices.exists(index=self.index):
            return
        await self.client.delete_by_query(
            index=self.index,
            body={"query": _doc_filter(document_id, version, below_version)},
            params={"refresh": "true", "conflicts": "proceed", "request_timeout": 30},
        )

    def search_body(
        self, query: str, institution_id: str, collection_ids: list[str], k: int
    ) -> dict[str, Any]:
        must = {
            "multi_match": {
                "query": query,
                "fields": ["text^1.0", "text.std^0.3"],
                "type": "best_fields",
                "operator": "or",
            }
        }
        flt = [{"term": {"institution_id": institution_id}}, {"terms": {"collection_id": collection_ids}}]
        return {
            "size": k,
            "query": {"bool": {"must": [must], "filter": flt if self.filters_enabled else []}},
            "_source": list(ChunkDoc.__dataclass_fields__),
        }

    async def search(
        self, query: str, institution_id: str, collection_ids: list[str], k: int
    ) -> list[Candidate]:
        resp = await self.client.search(
            index=self.index,
            body=self.search_body(query, institution_id, collection_ids, k),
            params={"request_timeout": self.timeout_s},
        )
        hits = resp.get("hits", {}).get("hits", [])
        return [
            Candidate.from_payload(h["_source"], rank=i, score=float(h["_score"] or 0))
            for i, h in enumerate(hits, 1)
        ]

    async def analyze(self, text: str) -> list[str]:
        """ADR-004 용 `_analyze` 결과(토큰 목록)."""
        resp = await self.client.indices.analyze(index=self.index, body={"field": "text", "text": text})
        return [t["token"] for t in resp.get("tokens", [])]

    async def close(self) -> None:
        await self.client.close()
