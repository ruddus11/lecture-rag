"""실제 provider 1회 호출 smoke (수동, 비밀 필요, CI 제외). 설계서 12장.

    uv run python -m scripts.live_smoke --embedding        # OpenAI 임베딩 1회
    uv run python -m scripts.live_smoke --openai --claude  # 답변 provider 각 1회 (M6)

키가 없으면 해당 항목을 SKIP 으로 출력하고 0 으로 종료한다. 출력에 키 값은 나오지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from app.core.config import Settings


def smoke_embedding(s: Settings) -> dict[str, Any]:
    key = s.openai_api_key.get_secret_value()
    if not key:
        return {"check": "openai_embedding", "status": "SKIP", "reason": "OPENAI_API_KEY 없음"}
    from app.retrieval.embeddings.openai_emb import OpenAIEmbedding

    emb = OpenAIEmbedding(key, s.openai_embedding_model)
    t = time.perf_counter()
    vec = emb.embed_query("운영체제의 교착 상태 필요 조건")
    return {
        "check": "openai_embedding",
        "status": "OK",
        "model": s.openai_embedding_model,
        "dim": len(vec),
        "latency_ms": round((time.perf_counter() - t) * 1000),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedding", action="store_true")
    ap.add_argument("--openai", action="store_true")
    ap.add_argument("--claude", action="store_true")
    args = ap.parse_args(argv)
    s = Settings()
    results: list[dict[str, Any]] = []
    if args.embedding:
        results.append(smoke_embedding(s))
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    return 1 if any(r["status"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
