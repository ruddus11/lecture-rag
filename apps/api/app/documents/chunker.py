"""페이지 경계 보존 토큰 청킹 (설계서 5.3, chunker_version="v1", ADR-005).

규칙
- 토크나이저 tiktoken cl100k_base. 페이지를 넘는 청크는 만들지 않는다.
- 페이지 전체가 max_tokens 이하이면 청크 1개.
- 아니면 문단(빈 줄) 단위로 누적해 target_tokens 를 넘기 직전에 끊고, 직전 청크의 마지막
  overlap_tokens 만큼을 다음 청크 앞에 붙인다(붙이면 max_tokens 를 넘는 경우는 생략).
- max_tokens 를 넘는 문단은 문장 경계로, 그래도 넘는 문장은 토큰 단위로 강제 분할한다.
- 페이지 마지막 청크의 새 내용이 min_tokens 미만이면 max_tokens 안에서 직전 청크에 합친다.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

import tiktoken

from app.core.config import (
    CHUNK_MAX_TOKENS,
    CHUNK_MIN_TOKENS,
    CHUNK_OVERLAP_TOKENS,
    CHUNK_TARGET_TOKENS,
)

CHUNK_NAMESPACE = uuid.UUID("6f0c2c3e-5d0b-4e4b-9a2d-3b0c1b4d9e11")
_PARA = re.compile(r"\n\s*\n")
_SENT = re.compile(r"(?<=[.?!])[ ]+|\n")


def chunk_id(document_id: str, index_version: int, page_number: int, ordinal: int) -> str:
    return str(uuid.uuid5(CHUNK_NAMESPACE, f"{document_id}:{index_version}:{page_number}:{ordinal}"))


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


@dataclass(frozen=True)
class ChunkSpan:
    page_number: int
    ordinal: int
    text: str
    token_count: int
    char_start: int
    char_end: int


class Chunker:
    def __init__(
        self,
        target_tokens: int = CHUNK_TARGET_TOKENS,
        overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
        max_tokens: int = CHUNK_MAX_TOKENS,
        min_tokens: int = CHUNK_MIN_TOKENS,
    ) -> None:
        assert overlap_tokens < target_tokens <= max_tokens
        self.target = target_tokens
        self.overlap = overlap_tokens
        self.max = max_tokens
        self.min = min_tokens
        self.enc = _encoding()

    def _tokens(self, text: str) -> list[int]:
        return self.enc.encode(text, disallowed_special=())

    def ntok(self, text: str) -> int:
        return len(self._tokens(text))

    # --- 단위 분할 -------------------------------------------------------
    @staticmethod
    def _split(text: str, start: int, end: int, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        pos = start
        for m in pattern.finditer(text, start, end):
            if m.start() > pos:
                spans.append((pos, m.start()))
            pos = m.end()
        if pos < end:
            spans.append((pos, end))
        return [s for s in (_trim(text, a, b) for a, b in spans) if s[0] < s[1]]

    def _token_split(self, text: str, start: int, end: int) -> list[tuple[int, int]]:
        toks = self._tokens(text[start:end])
        _, offs = self.enc.decode_with_offsets(toks)
        cuts = [start + offs[i] for i in range(0, len(toks), self.target)] + [end]
        return [(a, b) for a, b in zip(cuts, cuts[1:], strict=False) if a < b]

    def _units(self, text: str) -> list[tuple[int, int]]:
        units: list[tuple[int, int]] = []
        for ps, pe in self._split(text, 0, len(text), _PARA):
            if self.ntok(text[ps:pe]) <= self.max:
                units.append((ps, pe))
                continue
            for ss, se in self._split(text, ps, pe, _SENT):
                if self.ntok(text[ss:se]) <= self.max:
                    units.append((ss, se))
                else:
                    units.extend(self._token_split(text, ss, se))
        return units

    def _overlap_start(self, text: str, start: int, end: int) -> int:
        toks = self._tokens(text[start:end])
        if len(toks) <= self.overlap:
            return start
        _, offs = self.enc.decode_with_offsets(toks)
        return start + offs[len(toks) - self.overlap]

    # --- 청킹 ------------------------------------------------------------
    def chunk_page(self, page_number: int, text: str) -> list[ChunkSpan]:
        s, e = _trim(text, 0, len(text))
        if s >= e:
            return []  # 빈 페이지는 청크 없음
        if self.ntok(text[s:e]) <= self.max:
            return [self._span(page_number, 0, text, s, e)]

        spans: list[tuple[int, int, int]] = []  # (start, end, new_content_start)
        cur: list[int] | None = None  # [start, end, new_start]
        for us, ue in self._units(text):
            if cur is None:
                cur = [us, ue, us]
                continue
            if self.ntok(text[cur[0] : ue]) <= self.target:
                cur[1] = ue
                continue
            spans.append((cur[0], cur[1], cur[2]))
            ov = self._overlap_start(text, cur[0], cur[1])
            start = ov if self.ntok(text[ov:ue]) <= self.max else us
            cur = [start, ue, us]
        if cur is not None:
            last = (cur[0], cur[1], cur[2])
            if (
                spans
                and self.ntok(text[last[2] : last[1]]) < self.min
                and self.ntok(text[spans[-1][0] : last[1]]) <= self.max
            ):
                prev = spans.pop()
                last = (prev[0], last[1], prev[2])
            spans.append(last)

        out: list[ChunkSpan] = []
        for a, b, _ in spans:
            a, b = _trim(text, a, b)
            if a < b:
                out.append(self._span(page_number, len(out), text, a, b))
        return out

    def chunk_pages(self, pages: Iterable[tuple[int, str]]) -> list[ChunkSpan]:
        result: list[ChunkSpan] = []
        for page_number, text in pages:
            result.extend(self.chunk_page(page_number, text))
        return result

    def _span(self, page_number: int, ordinal: int, text: str, a: int, b: int) -> ChunkSpan:
        body = text[a:b]
        return ChunkSpan(page_number, ordinal, body, self.ntok(body), a, b)


def _trim(text: str, a: int, b: int) -> tuple[int, int]:
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    return a, b
