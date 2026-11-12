"""페이지 단위 검색 지표. 정답 없는 문항은 검색 정확도 분모에서 제외한다."""

from __future__ import annotations

import numpy as np

Page = tuple[str, int]


def retrieval_metrics(
    hits: list[Page], gold: set[Page], required: set[Page] | None = None
) -> dict:
    result = {
        f"hit_{k}": int(bool(set(hits[:k]) & gold)) if gold else None for k in (1, 3, 5)
    }
    result["mrr_10"] = (
        next((1 / i for i, p in enumerate(hits[:10], 1) if p in gold), 0.0)
        if gold
        else None
    )
    result["required_recall_5"] = (
        len(set(hits[:5]) & required) / len(required) if required else None
    )
    return result


def latency(values: list[float]) -> dict:
    if any(v < 0 or not np.isfinite(v) for v in values):
        raise ValueError("latency must be finite and nonnegative")
    return {
        "n": len(values),
        "p50": float(np.percentile(values, 50, method="nearest")) if values else None,
        "p95": float(np.percentile(values, 95, method="nearest")) if values else None,
    }


def abstention_rates(rows: list[tuple[bool, bool]]) -> dict:
    def rate(answerable: bool):
        subset = [abstained for a, abstained in rows if a == answerable]
        return sum(subset) / len(subset) if subset else None

    return {"abstention_rate": rate(False), "false_abstention_rate": rate(True)}
