from __future__ import annotations

import uuid

from app.documents.chunker import Chunker, chunk_id
from app.documents.normalize import normalize_query, normalize_text
from app.documents.parser import parse_pdf

LONG_PARA = "선점형 스케줄링은 실행 중인 프로세스를 중단시킬 수 있다. " * 40  # 문단 하나가 max 초과
LONG_PAGE = "\n\n".join(f"{i}번째 문단입니다. " + "운영체제는 자원을 관리한다. " * 12 for i in range(20))


# --- 정규화 -----------------------------------------------------------------
def test_normalize_nfc_whitespace_control():
    nfd = "한"  # '한' 의 NFD
    raw = f"{nfd}글\r\n둘째\t줄   \n\n\n\n셋째\x00\x07줄\x0c"
    out = normalize_text(raw)
    assert out == "한글\n둘째 줄\n\n셋째줄"


def test_normalize_keeps_symbols_and_code():
    assert normalize_text("f(x) = x^2 + 1; a[i] != b  ") == "f(x) = x^2 + 1; a[i] != b"


def test_normalize_query():
    assert normalize_query("  운영체제   스케줄링\n이란? ") == "운영체제 스케줄링 이란?"


# --- 청킹 -------------------------------------------------------------------
def test_short_page_single_chunk_and_empty_page_skipped():
    c = Chunker()
    spans = c.chunk_pages([(1, "짧은 페이지"), (2, "   \n  "), (3, "세번째")])
    assert [(s.page_number, s.ordinal) for s in spans] == [(1, 0), (3, 0)]
    assert spans[0].token_count < c.min


def test_chunks_never_cross_pages_and_offsets_match():
    c = Chunker()
    pages = [(1, LONG_PAGE), (2, LONG_PAGE + "\n\n마지막"), (3, "끝")]
    spans = c.chunk_pages(pages)
    by_page = dict(pages)
    for s in spans:
        src = by_page[s.page_number]
        assert src[s.char_start : s.char_end] == s.text
    assert {s.page_number for s in spans} == {1, 2, 3}
    for p in (1, 2):
        ords = [s.ordinal for s in spans if s.page_number == p]
        assert ords == list(range(len(ords))) and len(ords) > 1


def test_all_chunks_within_max_tokens():
    c = Chunker()
    for text in (LONG_PAGE, LONG_PARA, "가" * 5000, "a" * 20000):
        spans = c.chunk_page(1, text)
        assert spans and all(s.token_count <= c.max for s in spans), text[:20]


def test_overlap_is_prefix_of_next_chunk():
    c = Chunker()
    spans = c.chunk_page(1, LONG_PAGE)
    assert len(spans) >= 3
    for prev, nxt in zip(spans, spans[1:], strict=False):
        # 다음 청크는 이전 청크 끝부분(overlap)에서 시작한다
        assert nxt.char_start < prev.char_end
        overlap = LONG_PAGE[nxt.char_start : prev.char_end]
        assert 0 < c.ntok(overlap) <= c.overlap + 2


def test_long_paragraph_split_by_sentence():
    c = Chunker()
    spans = c.chunk_page(1, LONG_PARA)
    assert len(spans) >= 2
    assert all(s.text.endswith("다.") for s in spans)


def test_chunk_id_deterministic():
    a = chunk_id("doc-1", 1, 3, 0)
    assert a == chunk_id("doc-1", 1, 3, 0)
    assert a != chunk_id("doc-1", 2, 3, 0) != chunk_id("doc-1", 1, 3, 1)
    ns = uuid.UUID("6f0c2c3e-5d0b-4e4b-9a2d-3b0c1b4d9e11")  # 설계서 4.1 고정 네임스페이스
    assert a == str(uuid.uuid5(ns, "doc-1:1:3:0")) and uuid.UUID(a).version == 5
    c = Chunker()
    assert c.chunk_page(1, LONG_PAGE) == c.chunk_page(1, LONG_PAGE)


# --- 파서 -------------------------------------------------------------------
def test_parser_page_mapping(pdfs):
    from tests.fixtures.make_pdfs import KOREAN_PAGES

    doc = parse_pdf(pdfs["korean_text.pdf"], 200)
    assert doc.page_count == 3 and [p.page_number for p in doc.pages] == [1, 2, 3]
    assert doc.pages[0].text.startswith("운영체제 개요")
    assert "교착 상태의 네 가지 필요 조건" in doc.pages[2].text.replace("\n", " ")
    assert "라운드 로빈" in doc.pages[1].text
    assert KOREAN_PAGES[0].split("\n")[0] in doc.pages[0].text


def test_parser_blank_pages(pdfs):
    doc = parse_pdf(pdfs["blank_pages.pdf"], 200)
    assert doc.page_count == 4
    assert doc.pages[1].text == "" and doc.pages[3].text == ""
