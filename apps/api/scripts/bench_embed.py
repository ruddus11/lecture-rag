"""로컬 임베딩 처리량 측정 (청크/초, 프로세스 RSS). 결과는 docs/performance.md 에 옮긴다.

python -m scripts.bench_embed BAAI/bge-m3 data/samples/os_week3_process.pdf ...
"""

from __future__ import annotations

import json
import platform
import resource
import sys
import time
from pathlib import Path

from app.documents.chunker import Chunker
from app.documents.parser import parse_pdf
from app.retrieval.embeddings.local_st import LocalSTEmbedding


def rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024, 1)  # macOS: bytes


def main() -> None:
    model, pdfs = sys.argv[1], sys.argv[2:]
    chunker = Chunker()
    texts: list[str] = []
    for p in pdfs:
        d = parse_pdf(Path(p), 200)
        texts += [s.text for s in chunker.chunk_pages([(pg.page_number, pg.text) for pg in d.pages])]
    emb = LocalSTEmbedding(model)
    t = time.perf_counter()
    emb.load()
    load_s = time.perf_counter() - t
    emb.embed_documents(texts[:4])  # warm-up
    t = time.perf_counter()
    emb.embed_documents(texts)
    sec = time.perf_counter() - t
    q = time.perf_counter()
    for _ in range(20):
        emb.embed_query("교착 상태의 네 가지 조건")
    qms = (time.perf_counter() - q) / 20 * 1000
    print(
        json.dumps(
            {
                "model": model,
                "dim": emb.dim,
                "chunks": len(texts),
                "tokens_avg": round(sum(chunker.ntok(x) for x in texts) / len(texts), 1),
                "load_s": round(load_s, 1),
                "embed_s": round(sec, 2),
                "chunks_per_s": round(len(texts) / sec, 1),
                "query_ms": round(qms, 1),
                "max_rss_mb": rss_mb(),
                "machine": platform.machine(),
                "python": platform.python_version(),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
