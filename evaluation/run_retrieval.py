"""python -m evaluation.run_retrieval --split dev --modes keyword,vector,hybrid"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from evaluation.client import EvaluationClient, dataset
from evaluation.metrics import retrieval_metrics


def evaluate(client, questions, mode, top_k):
    rows = []
    for q in questions:
        row = {
            "query_id": q["query_id"],
            "question": q["question"],
            "answerable": q["answerable"],
            "category": q["category"],
            "status": "ok",
            "error": "",
        }
        slug = q["collection_slug"]
        references = q["gold"] + q["required_pages"]
        if slug not in client.collections or any(
            (slug, g["document_sha256"]) not in client.documents for g in references
        ):
            row["status"] = "skipped"
            rows.append(row)
            continue
        gold = {
            (client.documents[slug, g["document_sha256"]], p)
            for g in q["gold"]
            for p in g["page_numbers"]
        }
        required = {
            (client.documents[slug, g["document_sha256"]], g["page_number"])
            for g in q["required_pages"]
        }
        try:
            r = client.http.post(
                "/search",
                json={
                    "query": q["question"],
                    "mode": mode,
                    "collection_ids": [client.collections[slug]],
                    "top_k": top_k,
                },
            )
            r.raise_for_status()
            body = r.json()
            hits = [(h["document_id"], h["page_number"]) for h in body["hits"]]
            row["pages"] = json.dumps(hits)
            row["timings_ms"] = json.dumps(body["timings_ms"])
            row["cache_status"] = body["cache_status"]
            if body["degraded"]:
                row.update(status="failed", error="degraded")
        except Exception as exc:
            row.update(status="failed", error=type(exc).__name__)
            hits = []
        row.update(
            retrieval_metrics(hits if row["status"] == "ok" else [], gold, required)
        )
        rows.append(row)
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000/api/v1")
    p.add_argument("--split", choices=["dev", "test"], default="dev")
    p.add_argument("--modes", default="keyword,vector,hybrid")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--out", type=Path, default=Path("evaluation/results"))
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    client = EvaluationClient(args.base)
    try:
        for mode in args.modes.split(","):
            rows = evaluate(client, dataset(args.split), mode, args.top_k)
            stem = f"{datetime.now(UTC):%Y%m%d_%H%M%S}_{args.split}_{mode}"
            fields = list(dict.fromkeys(k for row in rows for k in row))
            with (args.out / f"{stem}.csv").open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            metrics = {}
            for key in ["hit_1", "hit_3", "hit_5", "mrr_10", "required_recall_5"]:
                vals = [r[key] for r in rows if r.get(key) is not None]
                metrics[key] = sum(vals) / len(vals) if vals else None
            summary = {
                "mode": mode,
                "n": len(rows),
                "failed": sum(r["status"] == "failed" for r in rows),
                "skipped": sum(r["status"] == "skipped" for r in rows),
                **metrics,
                "environment": client.meta,
            }
            (args.out / f"{stem}_summary.md").write_text(
                "# 검색 평가\n\n```json\n"
                + json.dumps(summary, ensure_ascii=False, indent=2)
                + "\n```\n"
            )
            print(json.dumps(summary, ensure_ascii=False))
    finally:
        client.close()


if __name__ == "__main__":
    main()
