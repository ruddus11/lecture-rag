"""프로세스 내 토큰 버킷 rate limit (설계서 8.4)."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import AppError


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.rate_limit_enabled
        # 이름 → (용량, 초당 보충량)
        self.rules: dict[str, tuple[int, float]] = {
            "query": (settings.rate_limit_query_per_minute, settings.rate_limit_query_per_minute / 60),
            "answers": (settings.rate_limit_answers_per_minute, settings.rate_limit_answers_per_minute / 60),
            "upload": (settings.rate_limit_upload_per_hour, settings.rate_limit_upload_per_hour / 3600),
        }
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        self._lock = threading.Lock()

    def _take(self, user_id: str, rule: str, now: float) -> float:
        """토큰 1개를 쓰고 0을 돌려준다. 부족하면 소비하지 않고 대기 초를 돌려준다."""
        capacity, rate = self.rules[rule]
        b = self._buckets.get((user_id, rule))
        if b is None:
            b = self._buckets[(user_id, rule)] = _Bucket(tokens=float(capacity), updated=now)
        b.tokens = min(capacity, b.tokens + (now - b.updated) * rate)
        b.updated = now
        if b.tokens >= 1:
            return 0.0
        return (1 - b.tokens) / rate if rate > 0 else 3600.0

    def check(self, user_id: str, *rules: str) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        with self._lock:
            waits = [self._take(user_id, r, now) for r in rules]
            wait = max(waits) if waits else 0.0
            if wait > 0:
                retry = max(1, math.ceil(wait))
                raise AppError(
                    429,
                    "rate_limited",
                    "요청이 너무 많습니다. 잠시 후 다시 시도하세요.",
                    retryable=True,
                    headers={"Retry-After": str(retry)},
                )
            for r in rules:
                self._buckets[(user_id, r)].tokens -= 1
