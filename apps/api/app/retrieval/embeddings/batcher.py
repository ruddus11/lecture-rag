"""질문 임베딩 기회적 묶음 처리 (ADR-011).

인코더가 놀고 있으면 바로 1건을 보내고, 인코딩 중에 들어온 질문은 쌓아 두었다가 끝나는 즉시 한 번에 보낸다.
대기 창(timer)이 없어 동시성 1의 지연은 그대로이고, 동시 요청은 CPU 스레드를 나눠 쓰는 대신
한 batch 로 처리된다.
같은 batch 안의 동일 문장은 한 번만 인코딩한다. 기다리던 요청이 취소(타임아웃)되면 그 결과만 버린다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

log = logging.getLogger(__name__)

MAX_BATCH = 16


class QueryBatcher:
    def __init__(
        self, embed_many: Callable[[list[str]], list[list[float]]], max_batch: int = MAX_BATCH
    ) -> None:
        self.embed_many = embed_many
        self.max_batch = max_batch
        self._pending: list[tuple[str, asyncio.Future[list[float]]]] = []
        self._task: asyncio.Task[None] | None = None
        self.batches: list[int] = []  # 최근 batch 크기 (테스트·진단용, 길이 제한)

    async def embed(self, text: str) -> list[float]:
        loop = asyncio.get_running_loop()
        if self._task is not None and self._task.get_loop() is not loop:  # 테스트 등에서 loop 가 바뀐 경우
            self._task, self._pending = None, [(t, f) for t, f in self._pending if f.get_loop() is loop]
        fut: asyncio.Future[list[float]] = loop.create_future()
        self._pending.append((text, fut))
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._drain())
        return await fut

    async def _drain(self) -> None:
        while self._pending:
            batch, self._pending = self._pending[: self.max_batch], self._pending[self.max_batch :]
            batch = [(t, f) for t, f in batch if not f.done()]
            if not batch:
                continue
            texts = list(dict.fromkeys(t for t, _ in batch))
            self.batches = (self.batches + [len(texts)])[-100:]
            try:
                vecs = await asyncio.to_thread(self.embed_many, texts)
                if len(vecs) != len(texts):
                    raise RuntimeError(f"embedding count mismatch: {len(vecs)} != {len(texts)}")
            except Exception as exc:  # noqa: BLE001 - 기다리는 요청 모두에 같은 오류를 전달
                for _, f in batch:
                    if not f.done():
                        f.set_exception(exc)
                continue
            by_text = dict(zip(texts, vecs, strict=True))
            for t, f in batch:
                if not f.done():
                    f.set_result(by_text[t])
