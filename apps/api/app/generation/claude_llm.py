"""Claude provider (anthropic SDK 2.8.0 에서 확인).

`AsyncAnthropic.messages.parse(model, max_tokens=2048, system, messages, output_format=AnswerDraft,
output_config={"effort": "low"})` → `response.parsed_output`. thinking·fallbacks 는 보내지 않는다(ADR-007).
`stop_reason == "refusal"` 은 refused 로, 예외는 RateLimit→429, 5xx·연결→503, 그 밖→500 으로 바꾼다.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.generation.base import AnswerDraft, Evidence, ProviderError, ProviderResult
from app.generation.prompts import SYSTEM_PROMPT, user_prompt

log = logging.getLogger(__name__)
MAX_TOKENS = 2048


def map_anthropic_error(e: Exception) -> ProviderError:
    import anthropic

    if isinstance(e, anthropic.RateLimitError):
        return ProviderError(429, "provider_rate_limited", "Claude rate limit")
    if isinstance(e, anthropic.APIConnectionError):  # APITimeoutError 포함
        return ProviderError(503, "answer_unavailable", f"Claude 연결 실패: {type(e).__name__}")
    if isinstance(e, anthropic.APIStatusError) and e.status_code >= 500:
        return ProviderError(503, "answer_unavailable", f"Claude {e.status_code}")
    return ProviderError(500, "provider_error", f"Claude 오류: {type(e).__name__}")


class ClaudeLLM:
    name = "claude"

    def __init__(self, api_key: str, model: str, timeout_s: float = 30.0, client: Any = None) -> None:
        self.model = model
        if client is None:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=api_key, timeout=timeout_s, max_retries=1)
        self.client = client

    async def generate(self, question: str, evidences: list[Evidence]) -> ProviderResult:
        t = time.perf_counter()
        try:
            resp = await self.client.messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt(question, evidences)}],
                output_format=AnswerDraft,
                output_config={"effort": "low"},
            )
        except Exception as e:
            err = map_anthropic_error(e)
            log.warning(
                "claude_error", extra={"event": "claude_error", "code": err.code, "error": str(e)[:300]}
            )
            raise err from e
        usage = {
            "input_tokens": int(getattr(resp.usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(resp.usage, "output_tokens", 0) or 0),
        }
        ms = int((time.perf_counter() - t) * 1000)
        model = str(getattr(resp, "model", None) or self.model)
        if resp.stop_reason == "refusal":
            return ProviderResult(None, model, usage, ms, refused=True)
        draft = resp.parsed_output if isinstance(resp.parsed_output, AnswerDraft) else None
        return ProviderResult(draft, model, usage, ms)
