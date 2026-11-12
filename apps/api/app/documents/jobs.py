"""SQLite 기반 작업 큐와 단일 워커 (설계서 5.1).

- lifespan 시작 시 processing → queued 복구(attempts 유지) 후 워커 태스크 1개를 띄운다.
- 워커는 queued 를 created_at 순으로 1초 간격 폴링하고 한 번에 1개만 처리한다.
- blocking 작업은 max_workers=1 executor 에서 실행한다.
- 재시도 가능한 오류는 attempts < max_attempts 이면 다시 queued 로 둔다. 그 밖에는 failed.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, TypeVar

from sqlalchemy import select

from app.storage.models import Document, IngestionJob, utcnow

if TYPE_CHECKING:
    from app.container import Services

log = logging.getLogger(__name__)
T = TypeVar("T")

# 단계별 미분류 예외의 오류 코드와 재시도 가능 여부
STAGE_ERROR = {
    "received": ("parse_failed", False),
    "parsing": ("parse_failed", False),
    "chunking": ("no_text", False),
    "embedding": ("embedding_failed", True),
    "indexing_vector": ("vector_index_failed", True),
    "indexing_keyword": ("keyword_index_failed", True),
    "activating": ("activate_failed", True),
    "removing_indexes": ("delete_failed", True),
    "removing_file": ("delete_failed", True),
}


class JobError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class JobCancelled(Exception):
    """처리 도중 문서가 삭제되는 등 더 진행할 이유가 없어진 경우."""


class JobContext:
    """실행 중인 작업 1개의 상태 전이 도우미."""

    def __init__(self, runner: JobRunner, job_id: str) -> None:
        self.runner = runner
        self.services = runner.services
        self.job_id = job_id
        self.stage: str | None = None
        self._stage_started = time.perf_counter()
        self.stage_ms: dict[str, float] = {}

    def set_stage(self, stage: str) -> None:
        now = time.perf_counter()
        if self.stage:
            self.stage_ms[self.stage] = round((now - self._stage_started) * 1000, 1)
            log.info(
                "job_stage_done",
                extra={
                    "event": "job_stage_done",
                    "job_id": self.job_id,
                    "stage": self.stage,
                    "ms": self.stage_ms[self.stage],
                },
            )
        self.stage = stage
        self._stage_started = now
        with self.services.db.session() as s:
            job = s.get(IngestionJob, self.job_id)
            assert job is not None
            job.stage = stage
            s.commit()

    def finish_stage(self) -> None:
        if self.stage:
            self.stage_ms[self.stage] = round((time.perf_counter() - self._stage_started) * 1000, 1)

    async def blocking(self, fn: Callable[..., T], *args: Any) -> T:
        return await self.runner.run_blocking(fn, *args)


class JobRunner:
    def __init__(self, services: Services, poll_interval: float = 1.0) -> None:
        self.services = services
        self.poll_interval = poll_interval
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingest")
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    # --- 수명 ------------------------------------------------------------
    def recover(self) -> int:
        """재시작 복구: processing 작업을 queued 로 되돌린다 (attempts 유지)."""
        with self.services.db.session() as s:
            jobs = s.scalars(select(IngestionJob).where(IngestionJob.status == "processing")).all()
            for job in jobs:
                job.status = "queued"
                job.stage = None
                doc = s.get(Document, job.document_id)
                if doc is not None and job.kind == "ingest" and doc.status == "processing":
                    doc.status = "queued"
            s.commit()
        if jobs:
            log.warning("jobs_recovered", extra={"event": "jobs_recovered", "count": len(jobs)})
        return len(jobs)

    def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._loop(), name="ingest-worker")

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self.executor.shutdown(wait=False, cancel_futures=True)

    def notify(self) -> None:
        self._wake.set()

    async def run_blocking(self, fn: Callable[..., T], *args: Any) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, fn, *args)

    # --- 루프 ------------------------------------------------------------
    async def _loop(self) -> None:
        while not self._stopping:
            try:
                ran = await self.run_once()
            except Exception:  # noqa: BLE001 - 워커는 죽지 않는다
                log.exception("worker_error", extra={"event": "worker_error"})
                ran = False
            if not ran:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), self.poll_interval)
                self._wake.clear()

    async def run_once(self) -> bool:
        job_id = self._claim()
        if job_id is None:
            return False
        await self._run(job_id)
        return True

    async def drain(self, limit: int = 100) -> int:
        """테스트용: 대기 작업이 없을 때까지 처리한다."""
        n = 0
        while n < limit and await self.run_once():
            n += 1
        return n

    def _claim(self) -> str | None:
        with self.services.db.session() as s:
            while True:
                job = s.scalars(
                    select(IngestionJob)
                    .where(IngestionJob.status == "queued")
                    .order_by(IngestionJob.created_at, IngestionJob.id)
                    .limit(1)
                ).first()
                if job is None:
                    return None
                doc = s.get(Document, job.document_id)
                if job.attempts >= job.max_attempts:
                    job.status = "failed"
                    job.error_code = job.error_code or "max_attempts_exceeded"
                    job.finished_at = utcnow()
                    if doc is not None and job.kind == "ingest" and doc.status in ("queued", "processing"):
                        doc.status = "failed"
                        doc.error_code = job.error_code
                    s.commit()
                    continue
                job.status = "processing"
                job.attempts += 1
                job.started_at = utcnow()
                job.stage = None
                if doc is not None and job.kind == "ingest":
                    doc.status = "processing"
                s.commit()
                return job.id

    async def _run(self, job_id: str) -> None:
        from app.documents.delete import run_delete
        from app.documents.ingest import cleanup_failed_ingest, run_ingest

        ctx = JobContext(self, job_id)
        with self.services.db.session() as s:
            job = s.get(IngestionJob, job_id)
            assert job is not None
            kind = job.kind
        started = time.perf_counter()
        try:
            if kind == "ingest":
                await run_ingest(ctx)
            else:
                await run_delete(ctx)
        except JobCancelled as e:
            ctx.finish_stage()
            if kind == "ingest":
                await cleanup_failed_ingest(ctx)
            self._finish(job_id, ok=False, code="cancelled", message=str(e) or "cancelled", requeue=False)
        except Exception as e:
            ctx.finish_stage()
            if isinstance(e, JobError):
                code, message, retryable = e.code, e.message, e.retryable
            else:
                code, retryable = STAGE_ERROR.get(ctx.stage or "", ("internal_error", False))
                message = f"{type(e).__name__}: {e}"[:500]
                log.exception(
                    "job_unexpected_error", extra={"event": "job_unexpected_error", "job_id": job_id}
                )
            if kind == "ingest":
                await cleanup_failed_ingest(ctx)
            self._finish(job_id, ok=False, code=code, message=message, requeue=retryable)
        else:
            ctx.finish_stage()
            self._finish(job_id, ok=True)
        log.info(
            "job_finished",
            extra={
                "event": "job_finished",
                "job_id": job_id,
                "kind": kind,
                "stage_ms": ctx.stage_ms,
                "ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )

    def _finish(
        self,
        job_id: str,
        ok: bool,
        code: str | None = None,
        message: str | None = None,
        requeue: bool = False,
    ) -> None:
        with self.services.db.session() as s:
            job = s.get(IngestionJob, job_id)
            assert job is not None
            doc = s.get(Document, job.document_id)
            if ok:
                job.status = "succeeded"
                job.error_code = job.error_message = None
                job.finished_at = utcnow()
                s.commit()
                return
            job.error_code, job.error_message = code, message
            if requeue and job.attempts < job.max_attempts:
                job.status = "queued"
                job.stage = None
                if doc is not None and job.kind == "ingest" and doc.status == "processing":
                    doc.status = "queued"
                log.warning("job_requeued", extra={"event": "job_requeued", "job_id": job_id, "code": code})
            else:
                job.status = "failed"
                job.finished_at = utcnow()
                if doc is not None and job.kind == "ingest" and doc.status == "processing":
                    doc.status = "failed"
                    doc.error_code, doc.error_message = code, message
                log.warning("job_failed", extra={"event": "job_failed", "job_id": job_id, "code": code})
            s.commit()
