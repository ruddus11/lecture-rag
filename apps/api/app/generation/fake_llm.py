"""결정적 테스트용 provider (CI 전용). 첫 근거의 첫 문장을 답으로, c1 인용.

질문에 `[[no_evidence]]` 가 있으면 insufficient 를 돌려준다. 테스트 훅용 표식도 둔다:
`[[bad_id]]` 없는 근거 id, `[[bad_quote]]` 근거에 없는 quote, `[[refuse]]` 안전 거부, `[[error]]` 503.
"""

from __future__ import annotations

import re
import time

from app.generation.base import AnswerDraft, Citation, Evidence, ProviderError, ProviderResult

_SENT_END = re.compile(r"(?<=[.?!])\s|\n")


def first_sentence(text: str) -> str:
    text = " ".join(text.split())
    parts = [p.strip() for p in _SENT_END.split(text) if p.strip()]
    return parts[0] if parts else text


class FakeLLM:
    name = "fake"
    model = "fake"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, question: str, evidences: list[Evidence]) -> ProviderResult:
        self.calls += 1
        t = time.perf_counter()
        usage = {"input_tokens": 0, "output_tokens": 0}
        if "[[error]]" in question:
            raise ProviderError(503, "answer_unavailable", "fake provider error")
        if "[[refuse]]" in question:
            return ProviderResult(None, self.model, usage, 0, refused=True)
        if "[[no_evidence]]" in question or not evidences:
            draft = AnswerDraft(insufficient_evidence=True, answer="", citations=[])
        else:
            e = evidences[0]
            # 첫 근거 텍스트 중 줄바꿈 이전 첫 문장. 슬라이드 제목만 있는 줄은 건너뛴다.
            lines = [ln.strip() for ln in e.text.split("\n") if len(ln.strip()) > 15]
            sentence = first_sentence(lines[0] if lines else e.text)
            quote = sentence
            local_id = e.local_id
            if "[[bad_id]]" in question:
                local_id = "c99"
            if "[[bad_quote]]" in question:
                quote = "근거 어디에도 없는 완전히 지어낸 문장입니다."
            draft = AnswerDraft(
                insufficient_evidence=False,
                answer=sentence,
                citations=[Citation(local_id=local_id, quote=quote)],
            )
        return ProviderResult(draft, self.model, usage, int((time.perf_counter() - t) * 1000))
