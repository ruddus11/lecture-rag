"""인용 검증과 보류 판단 (설계서 7.3, 고정 규칙).

형식 검증만 한다. 의미적 사실성은 평가(수동)에서 판단한다.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from app.generation.base import Evidence, ProviderResult

SIMILARITY = 0.9
_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip()


@dataclass
class VerifiedCitation:
    evidence: Evidence
    quote: str


@dataclass
class Verdict:
    ok: bool
    reason: str | None = None  # 보류 사유
    citations: list[VerifiedCitation] = field(default_factory=list)
    dropped: int = 0
    answer: str = ""

    @property
    def retryable(self) -> bool:
        return self.reason == "invalid_citations"


def quote_matches(quote: str, text: str, threshold: float = SIMILARITY) -> bool:
    q, t = _norm(quote), _norm(text)
    if not q:
        return False
    if q in t:
        return True
    n = len(q)
    if n > len(t):
        return difflib.SequenceMatcher(None, q, t).ratio() >= threshold
    best = 0.0
    for i in range(len(t) - n + 1):  # 같은 길이 슬라이딩 윈도우 중 최대
        sm = difflib.SequenceMatcher(None, q, t[i : i + n], autojunk=False)
        if sm.real_quick_ratio() < threshold or sm.quick_ratio() < threshold:
            continue
        best = max(best, sm.ratio())
        if best >= threshold:
            return True
    return False


def verify(result: ProviderResult, evidences: list[Evidence]) -> Verdict:
    if result.refused:
        return Verdict(False, "provider_refused")
    draft = result.draft
    if draft is None:
        return Verdict(False, "provider_error")
    if draft.insufficient_evidence:
        return Verdict(False, "insufficient_evidence")
    if not draft.answer.strip():
        return Verdict(False, "empty_answer")
    if not draft.citations:
        return Verdict(False, "no_citations")
    by_id = {e.local_id: e for e in evidences}
    kept: list[VerifiedCitation] = []
    dropped = 0
    for c in draft.citations:
        ev = by_id.get(c.local_id.strip())
        if ev is None or not quote_matches(c.quote, ev.text):
            dropped += 1
            continue
        kept.append(VerifiedCitation(ev, _norm(c.quote)))
    if not kept:
        return Verdict(False, "invalid_citations", dropped=dropped)
    return Verdict(True, None, kept, dropped, draft.answer.strip())
