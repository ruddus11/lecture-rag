import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from evaluation.run_latency import requests_for, rss_mb, summarize  # noqa: E402


def _row(status="ok", error="", wall=10.0, timings=None, cache="off"):
    return {
        "status": status,
        "error": error,
        "wall_ms": wall,
        "timings": timings or {},
        "cache_status": cache,
    }


def test_summary_counts_errors_in_sample_and_percentiles_on_success():
    rows = [
        _row(wall=10, timings={"total": 8, "embed_query": 6}),
        _row(wall=20, timings={"total": 18}, cache="hit"),
        _row("failed", "degraded", wall=5, cache="miss"),
        _row("failed", "http_503", wall=1),
    ]
    s = summarize(rows, wall_s=2.0, concurrency=5)
    assert (s["n"], s["errors"], s["error_rate"], s["concurrency"]) == (4, 2, 0.5, 5)
    assert s["error_kinds"] == {"degraded": 1, "http_503": 1}
    assert s["client_ms"] == {"n": 2, "p50": 10.0, "p95": 20.0}
    assert s["server_ms"]["total"]["n"] == 2 and s["server_ms"]["embed_query"]["n"] == 1
    assert s["throughput_rps"] == 2.0
    assert s["cache_status"] == {"off": 2, "hit": 1, "miss": 1}


def test_requests_skip_unknown_collections_and_top_k_only_for_search():
    client = SimpleNamespace(collections={"os": "c1"})
    qs = [
        {"query_id": "q1", "question": "a", "collection_slug": "os"},
        {"query_id": "q2", "question": "b", "collection_slug": "missing"},
    ]
    assert requests_for(client, qs, "hybrid", "search", 10) == [
        ("q1", {"query": "a", "mode": "hybrid", "collection_ids": ["c1"], "top_k": 10})
    ]
    assert "top_k" not in requests_for(client, qs, "hybrid", "answers", 10)[0][1]
    with pytest.raises(SystemExit):
        requests_for(SimpleNamespace(collections={}), qs, "hybrid", "search", 10)


def test_rss_none_without_pid_or_process():
    assert rss_mb(None) is None
    assert rss_mb(2**22 + 12345) is None
