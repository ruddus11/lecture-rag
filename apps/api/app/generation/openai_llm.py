"""OpenAI provider (openai SDK 3.49.0 에서 확인).

Responses API `AsyncOpenAI.responses.parse(model, instructions, input, text_format=AnswerDraft,
max_output_tokens)` → `response.output_parsed`. 샘플링 파라미터는 기본값.
출력에 refusal 항목이 있으면 refused.
예외 분류는 Claude 와 같다(RateLimit→429, 5xx·연결→503, 그 밖→500).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.generation.base import AnswerDraft, Evidence, ProviderError, ProviderResult
from app.generation.prompts import SYSTEM_PROMPT, user_prompt

log = logging.getLogger(__name__)
MAX_OUTPUT_TOKENS = 2048


def map_openai_error(e: Exception) -> ProviderError:
    import openai

    if isinstance(e, openai.RateLimitError):
        return ProviderError(429, "provider_rate_limited", "OpenAI rate limit")
    if isinstance(e, openai.APIConnectionError):
        return ProviderError(503, "answer_unavailable", f"OpenAI 연결 실패: {type(e).__name__}")
    if isinstance(e, openai.APIStatusError) and e.status_code >= 500:
        return ProviderError(503, "answer_unavailable", f"OpenAI {e.status_code}")
    return ProviderError(500, "provider_error", f"OpenAI 오류: {type(e).__name__}")


def _refused(resp: Any) -> bool:
    for item in getattr(resp, "output", None) or []:
        for c in getattr(item, "content", None) or []:
            if getattr(c, "type", None) == "refusal":
                return True
    return False


class OpenAILLM:
    name = "openai"

    def __init__(self, api_key: str, model: str, timeout_s: float = 30.0, client: Any = None) -> None:
        self.model = model
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key, timeout=timeout_s, max_retries=1)
        self.client = client

    async def generate(self, question: str, evidences: list[Evidence]) -> ProviderResult:
        t = time.perf_counter()
        try:
            resp = await self.client.responses.parse(
                model=self.model,
                instructions=SYSTEM_PROMPT,
                input=user_prompt(question, evidences),
                text_format=AnswerDraft,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
        except Exception as e:
            err = map_openai_error(e)
            log.warning(
                "openai_error", extra={"event": "openai_error", "code": err.code, "error": str(e)[:300]}
            )
            raise err from e
        u = getattr(resp, "usage", None)
        usage = {
            "input_tokens": int(getattr(u, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(u, "output_tokens", 0) or 0),
        }
        ms = int((time.perf_counter() - t) * 1000)
        model = str(getattr(resp, "model", None) or self.model)
        if _refused(resp):
            return ProviderResult(None, model, usage, ms, refused=True)
        parsed = getattr(resp, "output_parsed", None)
        return ProviderResult(parsed if isinstance(parsed, AnswerDraft) else None, model, usage, ms)
