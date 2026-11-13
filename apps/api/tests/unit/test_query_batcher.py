"""QueryBatcher (ADR-011): 인코딩 중 들어온 질문을 한 batch 로 묶고, 오류·취소를 요청별로 전달한다."""

from __future__ import annotations

import asyncio
import threading

import pytest

from app.retrieval.embeddings.batcher import QueryBatcher


class Recorder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.gate = threading.Event()
        self.fail = False

    def __call__(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if len(self.calls) == 1:
            self.gate.wait(5)  # 첫 인코딩이 끝나기 전에 다른 질문이 쌓이게 한다
        if self.fail:
            raise RuntimeError("encoder down")
        return [[float(len(t))] for t in texts]


async def _start_then_queue(b: QueryBatcher, rec: Recorder, first: str, rest: list[str]):
    t1 = asyncio.create_task(b.embed(first))
    while not rec.calls:
        await asyncio.sleep(0.001)
    others = [asyncio.create_task(b.embed(t)) for t in rest]
    await asyncio.sleep(0.01)
    rec.gate.set()
    return t1, others


async def test_single_request_goes_immediately():
    rec = Recorder()
    rec.gate.set()
    b = QueryBatcher(rec)
    assert await b.embed("abc") == [3.0]
    assert rec.calls == [["abc"]]


async def test_requests_during_encoding_share_one_batch_and_dedupe():
    rec = Recorder()
    b = QueryBatcher(rec)
    t1, others = await _start_then_queue(b, rec, "a", ["bb", "ccc", "bb"])
    assert await t1 == [1.0]
    assert [await t for t in others] == [[2.0], [3.0], [2.0]]
    assert rec.calls == [["a"], ["bb", "ccc"]]


async def test_max_batch_splits():
    rec = Recorder()
    b = QueryBatcher(rec, max_batch=2)
    t1, others = await _start_then_queue(b, rec, "a", ["b", "c", "d"])
    await asyncio.gather(t1, *others)
    assert rec.calls == [["a"], ["b", "c"], ["d"]]


async def test_error_reaches_every_waiter_and_batcher_recovers():
    rec = Recorder()
    rec.fail = True
    b = QueryBatcher(rec)
    t1, others = await _start_then_queue(b, rec, "a", ["b"])
    for t in (t1, *others):
        with pytest.raises(RuntimeError):
            await t
    rec.fail = False
    assert await b.embed("xy") == [2.0]


async def test_cancelled_waiter_does_not_break_others():
    rec = Recorder()
    b = QueryBatcher(rec)
    t1, (t2, t3) = await _start_then_queue(b, rec, "a", ["b", "c"])
    t2.cancel()
    assert await t1 == [1.0] and await t3 == [1.0]
    with pytest.raises(asyncio.CancelledError):
        await t2
