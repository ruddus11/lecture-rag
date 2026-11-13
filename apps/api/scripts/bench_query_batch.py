"""질문 임베딩 batch 효과·동일성 확인 (ADR-011). 결과는 docs/performance.md 에 옮긴다.

python -m scripts.bench_query_batch BAAI/bge-m3 ../../evaluation/dataset.dev.jsonl

1건·batch(2/5/10/16)·5개 스레드 동시 1건씩의 평균 시간과,
batch 로 얻은 벡터가 1건씩 얻은 벡터와 같은지(코사인 최소값).
"""

from __future__ import annotations

import json
import platform
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from app.retrieval.embeddings.local_st import LocalSTEmbedding


def avg_ms(fn, rounds: int = 10) -> float:
    t = time.perf_counter()
    for _ in range(rounds):
        fn()
    return round((time.perf_counter() - t) / rounds * 1000, 1)


def main() -> None:
    model, path = sys.argv[1], Path(sys.argv[2])
    qs = [json.loads(line)["question"] for line in path.read_text().splitlines() if line]
    emb = LocalSTEmbedding(model)
    emb.load()
    for q in qs[:5]:  # warm-up
        emb.embed_query(q)
    out: dict = {"model": model, "machine": platform.machine(), "questions": len(qs)}
    out["single_ms"] = avg_ms(lambda: emb.embed_query(qs[0]))
    out["batch_ms"] = {b: avg_ms(lambda b=b: emb.embed_queries(qs[:b])) for b in (2, 5, 10, 16)}
    with ThreadPoolExecutor(5) as ex:
        out["threads5_single_each_round_ms"] = avg_ms(lambda: list(ex.map(emb.embed_query, qs[:5])))
    single = np.array([emb.embed_query(q) for q in qs[:16]])
    batched = np.array(emb.embed_queries(qs[:16]))
    cos = (single * batched).sum(axis=1)  # normalize_embeddings=True
    out["batch_vs_single_cosine_min"] = round(float(cos.min()), 6)
    out["batch_vs_single_max_abs_diff"] = float(np.abs(single - batched).max())
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
