"""PDF → 페이지 텍스트 (PyMuPDF). 텍스트 추출만 하고 링크·스크립트는 다루지 않는다."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.core.config import PARSE_TIMEOUT_SECONDS
from app.documents.normalize import normalize_text

MIN_TEXT_RATIO = 0.2
MIN_PAGE_CHARS = 5  # 이보다 짧은 페이지는 "텍스트 없음"으로 본다


@dataclass(frozen=True)
class ParsedPage:
    page_number: int  # 물리 페이지, 1부터
    text: str  # 정규화된 텍스트


@dataclass(frozen=True)
class ParsedDocument:
    page_count: int
    pages: list[ParsedPage]


class ParseError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_pdf(path: Path, max_pages: int, timeout_s: float = PARSE_TIMEOUT_SECONDS) -> ParsedDocument:
    started = time.monotonic()
    try:
        doc = pymupdf.open(path, filetype="pdf")
    except Exception as e:
        raise ParseError("parse_failed", f"PDF를 열 수 없습니다: {type(e).__name__}") from e
    try:
        if doc.needs_pass:
            raise ParseError("encrypted_pdf", "암호로 보호된 PDF는 지원하지 않습니다.")
        if doc.page_count == 0:
            raise ParseError("parse_failed", "페이지가 없는 PDF입니다.")
        if doc.page_count > max_pages:
            raise ParseError("too_many_pages", f"페이지 수({doc.page_count})가 상한({max_pages})을 넘습니다.")
        pages: list[ParsedPage] = []
        for i in range(doc.page_count):
            if time.monotonic() - started > timeout_s:
                raise ParseError("parse_timeout", f"파싱이 {int(timeout_s)}초를 넘었습니다.")
            try:
                raw = doc[i].get_text("text")
            except Exception as e:
                raise ParseError("parse_failed", f"{i + 1}쪽 텍스트 추출 실패") from e
            pages.append(ParsedPage(page_number=i + 1, text=normalize_text(str(raw))))
        with_text = sum(1 for p in pages if len(p.text.replace(" ", "").replace("\n", "")) >= MIN_PAGE_CHARS)
        if with_text / len(pages) < MIN_TEXT_RATIO:
            raise ParseError(
                "unsupported_scan",
                f"텍스트가 있는 페이지가 {with_text}/{len(pages)}쪽뿐입니다. 스캔 PDF는 지원하지 않습니다.",
            )
        return ParsedDocument(page_count=doc.page_count, pages=pages)
    finally:
        doc.close()
