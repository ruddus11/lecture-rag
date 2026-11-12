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


SMOKE_QUESTION = "교착 상태가 발생하기 위한 네 가지 조건은?"


def _evidences() -> list[Any]:
    from app.generation.base import Evidence

    return [
        Evidence(
            "c1",
            "smoke-1",
            "smoke-doc",
            "os_week3_process.pdf",
            7,
            "교착 상태가 발생하려면 다음 네 가지 조건이 동시에 성립해야 한다. 1. 상호 배제 2. 점유 대기 "
            "3. 비선점 4. 순환 대기",
        ),
        Evidence(
            "c2", "smoke-2", "smoke-doc", "os_week3_process.pdf", 8, "은행원 알고리즘은 교착 상태를 회피한다."
        ),
    ]


async def smoke_answer(provider: Any) -> dict[str, Any]:
    from app.generation.base import ProviderError
    from app.generation.citations import verify

    evs = _evidences()
    try:
        res = await provider.generate(SMOKE_QUESTION, evs)
    except ProviderError as e:
        return {"check": f"{provider.name}_answer", "status": "FAIL", "code": e.code, "http": e.status}
    v = verify(res, evs)
    return {
        "check": f"{provider.name}_answer",
        "status": "OK" if v.ok else "ABSTAIN",
        "model": res.model,
        "usage": res.usage,
        "latency_ms": res.latency_ms,
        "verify": v.reason or "ok",
        "draft": res.draft.model_dump() if res.draft else None,
    }


def smoke_answers(s: Settings, openai: bool, claude: bool) -> list[dict[str, Any]]:
    import asyncio

    out: list[dict[str, Any]] = []
    if openai:
        key, model = s.openai_api_key.get_secret_value(), s.openai_chat_model
        if not key or not model:
            out.append(
                {
                    "check": "openai_answer",
                    "status": "SKIP",
                    "reason": "OPENAI_API_KEY/OPENAI_CHAT_MODEL 없음",
                }
            )
        else:
            from app.generation.openai_llm import OpenAILLM

            out.append(asyncio.run(smoke_answer(OpenAILLM(key, model))))
    if claude:
        key = s.anthropic_api_key.get_secret_value()
        if not key:
            out.append({"check": "claude_answer", "status": "SKIP", "reason": "ANTHROPIC_API_KEY 없음"})
        else:
            from app.generation.claude_llm import ClaudeLLM

            out.append(asyncio.run(smoke_answer(ClaudeLLM(key, s.claude_model))))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedding", action="store_true")
    ap.add_argument("--openai", action="store_true")
    ap.add_argument("--claude", action="store_true")
    args = ap.parse_args(argv)
    s = Settings(
        answer_provider="fake", embedding_provider="local"
    )  # 기동 검증 우회: 키 유무는 항목별로 본다
    results: list[dict[str, Any]] = []
    if args.embedding:
        results.append(smoke_embedding(s))
    results.extend(smoke_answers(s, openai=args.openai, claude=args.claude))
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    return 1 if any(r["status"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
