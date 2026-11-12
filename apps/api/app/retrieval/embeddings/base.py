"""EmbeddingProvider 인터페이스 (설계서 5.4)."""

from __future__ import annotations

import re
from typing import Protocol


class EmbeddingProvider(Protocol):
    name: str  # "local" | "openai"
    model: str
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def is_loaded(self) -> bool: ...

    def load(self) -> None: ...


def model_slug(model: str) -> str:
    """`BAAI/bge-m3` → `bge_m3`, `text-embedding-3-small` → `text_embedding_3_small`."""
    base = model.rsplit("/", 1)[-1].lower()
    return re.sub(r"[^a-z0-9]+", "_", base).strip("_")


class EmbeddingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
