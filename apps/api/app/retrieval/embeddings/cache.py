"""문서 임베딩 해시 캐시 (설계서 5.4): /data/emb_cache/{model_slug}/{sha256[:2]}/{sha256}.npy

같은 (model, sha256(text)) 이면 재계산하지 않는다. 재시작에 살아남는다. 파일 손상은 미적중으로 본다.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from pathlib import Path

import numpy as np

from app.retrieval.embeddings.base import EmbeddingProvider, model_slug

log = logging.getLogger(__name__)


class EmbeddingFileCache:
    def __init__(self, root: Path, provider: EmbeddingProvider) -> None:
        self.provider = provider
        self.dir = root / model_slug(provider.model)
        self.hits = 0
        self.misses = 0

    def _path(self, text: str) -> Path:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return self.dir / h[:2] / f"{h}.npy"

    def _load(self, path: Path) -> list[float] | None:
        try:
            arr = np.load(path, allow_pickle=False)
        except (OSError, ValueError):
            return None
        if arr.ndim != 1 or (self.provider.dim and arr.shape[0] != self.provider.dim):
            return None
        return [float(x) for x in arr]

    def _save(self, path: Path, vec: list[float]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{uuid.uuid4().hex}.tmp.npy")
        np.save(tmp, np.asarray(vec, dtype=np.float32), allow_pickle=False)
        os.replace(tmp, path)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        paths = [self._path(t) for t in texts]
        out: list[list[float] | None] = [self._load(p) if p.exists() else None for p in paths]
        miss = [i for i, v in enumerate(out) if v is None]
        self.hits += len(texts) - len(miss)
        self.misses += len(miss)
        if miss:
            vecs = self.provider.embed_documents([texts[i] for i in miss])
            for i, v in zip(miss, vecs, strict=True):
                out[i] = v
                try:
                    self._save(paths[i], v)
                except OSError:
                    log.warning("emb_cache_write_failed", extra={"event": "emb_cache_write_failed"})
        return [v for v in out if v is not None]
