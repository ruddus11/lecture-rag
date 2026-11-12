"""실제 SDK 객체 형태를 흉내 낸 fake client 로 provider 어댑터의 매핑만 확인한다(네트워크 없음)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.generation.base import AnswerDraft, Evidence, ProviderError
from app.generation.claude_llm import ClaudeLLM
from app.generation.openai_llm import OpenAILLM

EV = [Evidence("c1", "k1", "d1", "a.pdf", 1, "근거 문장이다.")]
DRAFT = AnswerDraft(insufficient_evidence=False, answer="답", citations=[])


class _Call:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.kwargs = result, exc, None

    async def __call__(self, **kw):
        self.kwargs = kw
        if self.exc:
            raise self.exc
        return self.result


def _claude(result=None, exc=None):
    call = _Call(result, exc)
    return ClaudeLLM("k", "claude-test", client=SimpleNamespace(messages=SimpleNamespace(parse=call))), call


def _openai(result=None, exc=None):
    call = _Call(result, exc)
    return OpenAILLM("k", "gpt-test", client=SimpleNamespace(responses=SimpleNamespace(parse=call))), call


def _resp(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://example.test"))


async def test_claude_parse_kwargs_and_usage():
    usage = SimpleNamespace(input_tokens=10, output_tokens=3)
    p, call = _claude(
        SimpleNamespace(parsed_output=DRAFT, stop_reason="end_turn", usage=usage, model="claude-x")
    )
    r = await p.generate("q", EV)
    assert r.draft == DRAFT and r.usage == {"input_tokens": 10, "output_tokens": 3} and r.model == "claude-x"
    kw = call.kwargs
    assert kw["output_format"] is AnswerDraft and kw["max_tokens"] == 2048
    assert kw["output_config"] == {"effort": "low"} and "thinking" not in kw and "fallbacks" not in kw
    assert '<evidence id="c1"' in kw["messages"][0]["content"]


async def test_claude_refusal():
    p, _ = _claude(SimpleNamespace(parsed_output=None, stop_reason="refusal", usage=None, model="m"))
    assert (await p.generate("q", EV)).refused is True


@pytest.mark.parametrize(
    "exc_factory,status",
    [
        (lambda a: a.RateLimitError("rl", response=_resp(429), body=None), 429),
        (lambda a: a.InternalServerError("x", response=_resp(500), body=None), 503),
        (lambda a: a.APIConnectionError(request=httpx.Request("POST", "https://e")), 503),
        (lambda a: a.BadRequestError("bad", response=_resp(400), body=None), 500),
    ],
)
async def test_claude_error_mapping(exc_factory, status):
    import anthropic

    p, _ = _claude(exc=exc_factory(anthropic))
    with pytest.raises(ProviderError) as ei:
        await p.generate("q", EV)
    assert ei.value.status == status


async def test_openai_parse_and_refusal_and_errors():
    import openai

    usage = SimpleNamespace(input_tokens=5, output_tokens=2)
    ok = SimpleNamespace(output_parsed=DRAFT, output=[], usage=usage, model="gpt-x")
    p, call = _openai(ok)
    r = await p.generate("q", EV)
    assert r.draft == DRAFT and r.usage["input_tokens"] == 5 and call.kwargs["text_format"] is AnswerDraft
    refusal = SimpleNamespace(
        output_parsed=None, output=[SimpleNamespace(content=[SimpleNamespace(type="refusal")])], usage=usage
    )
    p, _ = _openai(refusal)
    assert (await p.generate("q", EV)).refused
    p, _ = _openai(exc=openai.RateLimitError("rl", response=_resp(429), body=None))
    with pytest.raises(ProviderError) as ei:
        await p.generate("q", EV)
    assert ei.value.status == 429
