"""OpenSearch 어댑터. 앱 전역 AsyncOpenSearch 1개."""

from __future__ import annotations

from typing import Any

from opensearchpy import AsyncOpenSearch


class OpenSearchStore:
    def __init__(self, url: str, timeout_ms: int = 2000, analyzer: str = "korean") -> None:
        self.url = url
        self.timeout_s = max(1.0, timeout_ms / 1000)
        self.analyzer = analyzer
        self.client = AsyncOpenSearch(hosts=[url], timeout=self.timeout_s)

    async def health(self) -> dict[str, Any]:
        health = await self.client.cluster.health()
        return {"status": health.get("status")}

    async def has_nori(self) -> bool:
        plugins = await self.client.cat.plugins(format="json")
        return any(p.get("component") == "analysis-nori" for p in plugins)

    async def close(self) -> None:
        await self.client.close()
