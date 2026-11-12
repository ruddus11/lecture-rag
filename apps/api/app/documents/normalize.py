"""텍스트 정규화 (설계서 5.3). 반복 헤더/푸터 제거는 하지 않는다 (ADR-005)."""

from __future__ import annotations

import re
import unicodedata

_CTRL = re.compile(r"[\x00-\x09\x0b-\x1f]")  # 줄바꿈(\x0a) 제외 제어 문자
_TRAILING_WS = re.compile(r"[  ]+\n")
_MANY_NL = re.compile(r"\n{3,}")
_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    # 1. NFC
    text = unicodedata.normalize("NFC", text)
    # 2. 줄바꿈 통일, 탭 → 공백
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    # 3. 제어 문자 제거 (탭은 2에서 이미 공백)
    text = _CTRL.sub("", text)
    # 2(계속). 줄 끝 공백 제거, 3개 이상 연속 줄바꿈 → 2개
    text = _TRAILING_WS.sub("\n", text)
    text = _MANY_NL.sub("\n\n", text)
    return text.strip()


def normalize_query(text: str) -> str:
    """질문 정규화 (설계서 6.1): NFC, 앞뒤 공백 제거, 연속 공백 1개."""
    return _WS.sub(" ", unicodedata.normalize("NFC", text)).strip()
