"""삭제 파이프라인 (설계서 5.5). M8 에서 구현한다."""

from __future__ import annotations

from app.documents.jobs import JobContext, JobError


async def run_delete(ctx: JobContext) -> None:
    raise JobError("not_implemented", "삭제 작업은 아직 구현되지 않았습니다.")
