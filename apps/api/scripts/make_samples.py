"""자작 샘플 강의자료 PDF 생성 → data/samples/*.pdf (공개 가능, 평가 데이터셋의 원천).

    uv run python -m scripts.make_samples [출력 폴더]

PDF 메타데이터의 생성 시각이 들어가므로 다시 만들면 sha256 이 바뀐다. 평가 문항은 sha256 으로 문서를
참조하므로 커밋된 PDF 를 재생성하지 않는다(재생성 시 dataset 의 document_sha256 도 갱신).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pymupdf

from scripts.sample_content import SAMPLES

REPO = Path(__file__).resolve().parents[3]


def write_pdf(path: Path, pages: list[str]) -> Path:
    doc = pymupdf.open()
    font = pymupdf.Font("korea")
    for text in pages:
        page = doc.new_page(width=842, height=595)  # A4 가로, 슬라이드 비율
        tw = pymupdf.TextWriter(page.rect)
        rest = tw.fill_textbox(page.rect + (50, 45, -50, -45), text, font=font, fontsize=13)
        if rest:
            raise ValueError(f"{path.name}: 페이지에 다 들어가지 않음: {rest[:1]}")
        tw.write_text(page)
    doc.set_metadata({"title": path.stem, "author": "lecture-rag-search samples"})
    doc.subset_fonts()
    doc.save(path, garbage=4, deflate=True)
    doc.close()
    return path


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "data" / "samples"
    out.mkdir(parents=True, exist_ok=True)
    for name, (slug, pages) in SAMPLES.items():
        p = write_pdf(out / name, pages)
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        print(f"{name}\t{slug}\t{len(pages)}p\t{p.stat().st_size}B\t{sha}")
