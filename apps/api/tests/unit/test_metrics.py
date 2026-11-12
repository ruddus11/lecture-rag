import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from evaluation.metrics import abstention_rates, latency, retrieval_metrics  # noqa: E402


def test_metrics_ranks_duplicates_and_required_pages():
    hits = [("d", 9), ("d", 2), ("d", 2), ("d", 3)]
    m = retrieval_metrics(hits, {("d", 2), ("d", 3)}, {("d", 2), ("d", 3)})
    assert m == {"hit_1": 0, "hit_3": 1, "hit_5": 1, "mrr_10": 0.5, "required_recall_5": 1}
    assert retrieval_metrics([], {("d", 2)})["mrr_10"] == 0
    assert retrieval_metrics([], set())["hit_1"] is None


def test_nearest_percentile_and_empty_sample():
    assert latency([1, 2, 10, 100]) == {"n": 4, "p50": 10.0, "p95": 100.0}
    assert latency([]) == {"n": 0, "p50": None, "p95": None}


def test_abstention_denominators():
    assert abstention_rates([(False, True), (False, False), (True, True)]) == {
        "abstention_rate": 0.5,
        "false_abstention_rate": 1.0,
    }
    assert abstention_rates([])["abstention_rate"] is None


def test_invalid_k_is_not_needed_and_missing_required_is_zero():
    assert retrieval_metrics([("d", 1)], {("d", 2)}, {("d", 3)})["required_recall_5"] == 0
    with pytest.raises(ValueError):
        latency([-1])
