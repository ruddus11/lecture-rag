import hashlib
import json
from collections import Counter
from pathlib import Path

import pymupdf


def test_public_dataset_matches_fixed_pdf_pages():
    root = Path(__file__).resolve().parents[4]
    rows = [
        json.loads(line)
        for split in ["dev", "test"]
        for line in (root / f"evaluation/dataset.{split}.jsonl").read_text().splitlines()
    ]
    assert Counter(r["split"] for r in rows) == {"dev": 30, "test": 10}
    assert Counter(r["category"] for r in rows) == {
        "definition": 10,
        "paraphrase": 10,
        "multi_evidence": 8,
        "numeric_or_code": 6,
        "unanswerable": 6,
    }
    assert len({r["query_id"] for r in rows}) == 40
    docs = {
        hashlib.sha256(p.read_bytes()).hexdigest(): pymupdf.open(p)
        for p in (root / "data/samples").glob("*.pdf")
    }
    try:
        for row in rows:
            assert bool(row["gold"]) == row["answerable"]
            for gold in row["gold"]:
                for page in gold["page_numbers"]:
                    assert (
                        docs[gold["document_sha256"]][page - 1].get_text().strip() in row["reference_answer"]
                    )
    finally:
        for doc in docs.values():
            doc.close()
