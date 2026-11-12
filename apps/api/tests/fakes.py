"""API 테스트용 in-memory 엔진·임베딩 fake (설계서 12장: 엔진 어댑터를 fake 로 교체)."""

from __future__ import annotations

import hashlib
import math


class FakeEmbedder:
    """결정적 해시 임베딩. 같은 단어를 공유하면 코사인 유사도가 올라간다."""

    name = "local"
    model = "fake-embed"

    def __init__(self, dim: int = 256, loaded: bool = True) -> None:
        self.dim = dim
        self.loaded = loaded
        self.calls = 0

    def load(self) -> None:
        self.loaded = True

    def is_loaded(self) -> bool:
        return self.loaded

    def _vec(self, text: str) -> list[float]:
        """단어 + 글자 bigram 해시. 한국어 조사가 붙어도 겹치는 bigram 으로 유사도가 생긴다."""
        v = [0.0] * self.dim
        compact = "".join(text.lower().split())
        grams = text.lower().split() + [compact[i : i + 2] for i in range(len(compact) - 1)]
        for tok in grams:
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        return self._vec(text)


class FakeVector:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    async def ping(self) -> bool:
        if not self.ok:
            raise ConnectionError("qdrant down")
        return True


class FakeKeyword:
    def __init__(self, ok: bool = True, nori: bool = True) -> None:
        self.ok = ok
        self.nori = nori

    async def health(self) -> dict:
        if not self.ok:
            raise ConnectionError("opensearch down")
        return {"status": "green"}

    async def has_nori(self) -> bool:
        return self.nori
