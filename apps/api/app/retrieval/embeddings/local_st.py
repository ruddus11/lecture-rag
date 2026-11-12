"""sentence-transformers 로컬 임베딩 (CPU). bge-m3 기본, e5 계열은 접두어를 붙인다."""

from __future__ import annotations

import logging
import threading
from typing import Any

log = logging.getLogger(__name__)

# 모델별 차원. 적재 전에 컬렉션 이름을 정해야 하므로 알려진 값은 미리 둔다.
KNOWN_DIMS = {
    "BAAI/bge-m3": 1024,
    "intfloat/multilingual-e5-small": 384,
    "intfloat/multilingual-e5-base": 768,
    "intfloat/multilingual-e5-large": 1024,
}


class LocalSTEmbedding:
    name = "local"

    def __init__(self, model: str, batch_size: int = 32, max_seq_length: int = 1024) -> None:
        self.model = model
        self.batch_size = batch_size
        self.max_seq_length = max_seq_length
        self._st: Any = None
        self._lock = threading.Lock()
        self._is_e5 = "e5" in model.lower()
        self.dim = KNOWN_DIMS.get(model, 0)

    def is_loaded(self) -> bool:
        return self._st is not None

    def load(self) -> None:
        with self._lock:
            if self._st is not None:
                return
            from sentence_transformers import SentenceTransformer

            log.info("embedding_model_loading", extra={"event": "embedding_model_loading"})
            st = SentenceTransformer(self.model, device="cpu")
            st.max_seq_length = min(self.max_seq_length, st.max_seq_length or self.max_seq_length)
            dim = int(st.get_embedding_dimension() or 0)
            if self.dim and dim != self.dim:
                raise RuntimeError(f"embedding dim mismatch: expected {self.dim}, got {dim}")
            self.dim = dim
            self._st = st
            log.info("embedding_model_loaded", extra={"event": "embedding_model_loaded", "dim": dim})

    def _encode(self, texts: list[str]) -> list[list[float]]:
        self.load()
        vecs = self._st.encode(
            texts, batch_size=self.batch_size, normalize_embeddings=True, show_progress_bar=False
        )
        return [list(map(float, v)) for v in vecs]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self._is_e5:
            texts = [f"passage: {t}" for t in texts]
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        if self._is_e5:
            text = f"query: {text}"
        return self._encode([text])[0]
