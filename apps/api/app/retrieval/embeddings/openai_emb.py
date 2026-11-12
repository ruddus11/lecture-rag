"""OpenAI 임베딩 (text-embedding-3-small 기본). batch 100, 429 시 지수 backoff 3회. dimensions 옵션 미사용."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.retrieval.embeddings.base import EmbeddingError

log = logging.getLogger(__name__)

KNOWN_DIMS = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072, "text-embedding-ada-002": 1536}
BATCH = 100
RETRIES = 3


class OpenAIEmbedding:
    name = "openai"

    def __init__(self, api_key: str, model: str = "text-embedding-3-small", timeout_s: float = 30.0) -> None:
        self.model = model
        self.dim = KNOWN_DIMS.get(model, 0)
        self._api_key = api_key
        self._timeout = timeout_s
        self._client: Any = None

    def load(self) -> None:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key, timeout=self._timeout, max_retries=0)

    def is_loaded(self) -> bool:
        return self._client is not None

    def _call(self, batch: list[str]) -> list[list[float]]:
        import openai

        self.load()
        delay = 1.0
        for attempt in range(RETRIES + 1):
            try:
                resp = self._client.embeddings.create(model=self.model, input=batch)
                vecs = [list(map(float, d.embedding)) for d in sorted(resp.data, key=lambda d: d.index)]
                if vecs and not self.dim:
                    self.dim = len(vecs[0])
                return vecs
            except openai.RateLimitError as e:
                if attempt == RETRIES:
                    raise EmbeddingError("embedding_rate_limited", "OpenAI 임베딩 rate limit") from e
                log.warning("embedding_backoff", extra={"event": "embedding_backoff", "attempt": attempt + 1})
                time.sleep(delay)
                delay *= 2
            except openai.OpenAIError as e:
                raise EmbeddingError("embedding_failed", f"OpenAI 임베딩 실패: {type(e).__name__}") from e
        raise AssertionError("unreachable")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            out.extend(self._call(texts[i : i + BATCH]))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._call([text])[0]
