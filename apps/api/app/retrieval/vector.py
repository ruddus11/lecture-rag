"""Qdrant 어댑터. 앱 전역 AsyncQdrantClient 1개."""

from __future__ import annotations

from qdrant_client import AsyncQdrantClient


class QdrantStore:
    def __init__(self, url: str, timeout_ms: int = 2000) -> None:
        self.url = url
        self.timeout_s = max(1, timeout_ms // 1000)
        self.client = AsyncQdrantClient(url=url, timeout=self.timeout_s, check_compatibility=False)

    async def ping(self) -> bool:
        await self.client.get_collections()
        return True

    async def close(self) -> None:
        await self.client.close()
