"""python -m evaluation.run_latency --endpoint search --mode hybrid --warmup 10 --n 200 --concurrency 1

HTTP 로 실제 API 를 호출해 클라이언트 측 지연(wall)과 서버 `timings_ms` 를 함께 기록한다
(설계서 10.2, 11.3). 질문은 평가 데이터셋 문항을 순서대로 반복한다. 오류 응답·`degraded=true` 는
오류로 집계하고 표본에서 빼지 않는다. API 프로세스 메모리는 `--api-pid`(네이티브) 또는
`EVAL_CONTAINER_MEMORY`(docker stats 수동 입력)로 남긴다.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import platform
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

from evaluation.client import EvaluationClient, dataset
from evaluation.metrics import latency


def requests_for(client, questions, mode, endpoint, top_k):
    """데이터셋 문항을 요청 본문으로 바꾼다. 문서가 없는 컬렉션 문항은 뺀다."""
    out = []
    for q in questions:
        slug = q["collection_slug"]
        if slug not in client.collections:
            continue
        body = {
            "query": q["question"],
            "mode": mode,
            "collection_ids": [client.collections[slug]],
        }
        if endpoint == "search":
            body["top_k"] = top_k
        out.append((q["query_id"], body))
    if not out:
        raise SystemExit("요청할 문항이 없다 (컬렉션 slug 를 확인)")
    return out


def rss_mb(pid: int | None) -> float | None:
    """ps 로 RSS(MB) 를 읽는다. pid 가 없거나 프로세스가 없으면 None."""
    if not pid:
        return None
    try:
        out = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=True,
        )
        return round(int(out.stdout.split()[0]) / 1024, 1)
    except (subprocess.CalledProcessError, IndexError, ValueError, FileNotFoundError):
        return None


def summarize(rows: list[dict], wall_s: float, concurrency: int) -> dict:
    """오류 포함 전체 표본 기준 오류율, 성공 응답 기준 p50/p95(클라이언트 wall·서버 단계별)."""
    ok = [r for r in rows if r["status"] == "ok"]
    stages: dict[str, list[float]] = {}
    for r in ok:
        for k, v in r["timings"].items():
            stages.setdefault(k, []).append(float(v))
    n = len(rows)
    return {
        "n": n,
        "concurrency": concurrency,
        "errors": n - len(ok),
        "error_rate": round((n - len(ok)) / n, 4) if n else None,
        "error_kinds": dict(Counter(r["error"] for r in rows if r["error"])),
        "client_ms": latency([r["wall_ms"] for r in ok]),
        "server_ms": {k: latency(v) for k, v in sorted(stages.items())},
        "throughput_rps": round(n / wall_s, 2) if wall_s > 0 else None,
        "cache_status": dict(
            Counter(r["cache_status"] for r in rows if r["cache_status"])
        ),
    }


async def _one(http: httpx.AsyncClient, path: str, qid: str, body: dict) -> dict:
    row = {
        "query_id": qid,
        "status": "ok",
        "error": "",
        "http_status": None,
        "cache_status": "",
        "timings": {},
    }
    t = time.perf_counter()
    try:
        r = await http.post(path, json=body)
        row["http_status"] = r.status_code
        if r.status_code != 200:
            row.update(status="failed", error=f"http_{r.status_code}")
        else:
            data = r.json()
            row["timings"] = data.get("timings_ms") or {}
            row["cache_status"] = data.get("cache_status") or ""
            if data.get("degraded"):
                row.update(status="failed", error="degraded")
    except Exception as exc:  # noqa: BLE001 - 오류 종류만 집계
        row.update(status="failed", error=type(exc).__name__)
    row["wall_ms"] = round((time.perf_counter() - t) * 1000, 2)
    return row


async def run(base, token, path, reqs, warmup, n, concurrency, pid):
    headers = {"Authorization": f"Bearer {token}"}
    limits = httpx.Limits(
        max_connections=concurrency, max_keepalive_connections=concurrency
    )
    async with httpx.AsyncClient(
        base_url=base, headers=headers, timeout=120, limits=limits
    ) as http:
        for i in range(warmup):
            qid, body = reqs[i % len(reqs)]
            await _one(http, path, qid, body)
        rows: list[dict] = [{} for _ in range(n)]
        counter = iter(range(n))
        mem: list[float] = []

        async def worker():
            for i in counter:
                qid, body = reqs[(warmup + i) % len(reqs)]
                rows[i] = await _one(http, path, qid, body) | {"seq": i}

        async def sample():
            while True:
                if (m := rss_mb(pid)) is not None:
                    mem.append(m)
                await asyncio.sleep(0.5)

        sampler = asyncio.create_task(sample())
        t0 = time.perf_counter()
        await asyncio.gather(*(worker() for _ in range(concurrency)))
        wall = time.perf_counter() - t0
        sampler.cancel()
        if (m := rss_mb(pid)) is not None:
            mem.append(m)
    return rows, wall, mem


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000/api/v1")
    p.add_argument("--endpoint", choices=["search", "answers"], default="search")
    p.add_argument("--mode", choices=["keyword", "vector", "hybrid"], default="hybrid")
    p.add_argument("--split", choices=["dev", "test"], default="dev")
    p.add_argument("--warmup", type=int, default=10)
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument(
        "--label", default="", help="before / after_parallel / after_cache 등 표 구분용"
    )
    p.add_argument(
        "--api-pid", type=int, default=None, help="네이티브 API 프로세스 RSS 측정용"
    )
    p.add_argument("--out", type=Path, default=Path("evaluation/results/latency"))
    args = p.parse_args()
    if args.n < 1 or args.concurrency < 1 or args.warmup < 0:
        raise SystemExit("n, concurrency 는 1 이상, warmup 은 0 이상")
    args.out.mkdir(parents=True, exist_ok=True)

    client = EvaluationClient(args.base)
    try:
        reqs = requests_for(
            client, dataset(args.split), args.mode, args.endpoint, args.top_k
        )
        token = client.http.headers["Authorization"].removeprefix("Bearer ")
        env = client.meta
    finally:
        client.close()

    rows, wall, mem = asyncio.run(
        run(
            args.base,
            token,
            f"/{args.endpoint}",
            reqs,
            args.warmup,
            args.n,
            args.concurrency,
            args.api_pid,
        )
    )
    summary = {
        "label": args.label,
        "endpoint": args.endpoint,
        "mode": args.mode,
        "split": args.split,
        "warmup": args.warmup,
        "distinct_queries": len(reqs),
        **summarize(rows, wall, args.concurrency),
        "api_rss_mb": {"max": max(mem), "end": mem[-1]} if mem else "unavailable",
        "environment": {
            **env,
            "client_host": f"{platform.system()} {platform.machine()} python {platform.python_version()}",
            "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    }
    stem = f"{datetime.now(UTC):%Y%m%d_%H%M%S}_{args.endpoint}_{args.mode}_c{args.concurrency}"
    if args.label:
        stem += f"_{args.label}"
    with (args.out / f"{stem}.csv").open("w", newline="") as f:
        fields = [
            "seq",
            "query_id",
            "status",
            "error",
            "http_status",
            "cache_status",
            "wall_ms",
            "timings",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({**r, "timings": json.dumps(r["timings"])})
    (args.out / f"{stem}_summary.md").write_text(
        "# 지연 측정\n\n```json\n"
        + json.dumps(summary, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    print(
        json.dumps(
            {k: summary[k] for k in summary if k != "environment"}, ensure_ascii=False
        )
    )
    if os.getenv("EVAL_FAIL_ON_ERROR") == "1" and summary["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
