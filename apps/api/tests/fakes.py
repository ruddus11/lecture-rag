"""API 테스트용 in-memory 엔진·임베딩 fake (설계서 12장: 엔진 어댑터를 fake 로 교체)."""

from __future__ import annotations

import hashlib
import math

from app.retrieval.types import Candidate, ChunkDoc


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
    """in-memory BM25 비슷한 keyword 엔진. 글자 bigram 겹침에 idf 가중치를 준다.
    OpenSearchStore 와 같은 메서드·필터 규칙(institution_id + collection_id)을 가진다."""

    analyzer = "korean"
    index = "chunks_v1"

    def __init__(self, ok: bool = True, nori: bool = True) -> None:
        self.ok = ok
        self.nori = nori
        self.docs: dict[str, ChunkDoc] = {}
        self.filters_enabled = True

    def _check(self) -> None:
        if not self.ok:
            raise ConnectionError("opensearch down")

    async def health(self) -> dict:
        self._check()
        return {"status": "green"}

    async def has_nori(self) -> bool:
        self._check()
        return self.nori

    async def ensure_index(self) -> None:
        self._check()

    async def bulk_index(self, docs: list[ChunkDoc]) -> None:
        self._check()
        for d in docs:
            self.docs[d.chunk_id] = d

    def _match(self, d: ChunkDoc, document_id: str, version: int | None, below: int | None) -> bool:
        return (
            d.document_id == document_id
            and (version is None or d.document_version == version)
            and (below is None or d.document_version < below)
        )

    async def count_document(self, document_id: str, version: int | None = None) -> int:
        self._check()
        return sum(self._match(d, document_id, version, None) for d in self.docs.values())

    async def delete_document(
        self, document_id: str, version: int | None = None, below_version: int | None = None
    ) -> None:
        self._check()
        for cid in [c for c, d in self.docs.items() if self._match(d, document_id, version, below_version)]:
            del self.docs[cid]

    @staticmethod
    def _grams(text: str) -> set[str]:
        t = "".join(text.lower().split())
        return {t[i : i + 2] for i in range(len(t) - 1)}

    async def search(
        self, query: str, institution_id: str, collection_ids: list[str], k: int
    ) -> list[Candidate]:
        self._check()
        pool = [
            d
            for d in self.docs.values()
            if not self.filters_enabled
            or (d.institution_id == institution_id and d.collection_id in collection_ids)
        ]
        q = self._grams(query)
        n = len(pool) or 1
        df = {g: sum(g in self._grams(d.text) for d in pool) for g in q}
        scored = []
        for d in pool:
            grams = self._grams(d.text)
            score = sum(math.log(1 + n / (1 + df[g])) for g in q if g in grams)
            if score > 0:
                scored.append((score, d.chunk_id, d))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [Candidate(chunk=d, rank=i, score=sc) for i, (sc, _, d) in enumerate(scored[:k], 1)]

    async def close(self) -> None:
        pass
