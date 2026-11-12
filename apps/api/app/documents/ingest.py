"""수집 파이프라인: received → parsing → chunking → embedding → indexing_vector
→ indexing_keyword → activating (설계서 5.2). 부분 성공은 없다."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import delete, select

from app.core.config import UPLOAD_MAX_PAGES
from app.documents.chunker import Chunker, ChunkSpan, chunk_id
from app.documents.jobs import JobCancelled, JobContext, JobError
from app.documents.parser import ParseError, parse_pdf
from app.storage.models import Chunk, Collection, Document, IngestionJob

log = logging.getLogger(__name__)


def _load(ctx: JobContext) -> tuple[IngestionJob, Document]:
    with ctx.services.db.session() as s:
        job = s.get(IngestionJob, ctx.job_id)
        assert job is not None
        doc = s.get(Document, job.document_id)
        assert doc is not None
        return job, doc


def _ensure_alive(ctx: JobContext, document_id: str) -> None:
    with ctx.services.db.session() as s:
        doc = s.get(Document, document_id)
        if doc is None or doc.deleted_at is not None or doc.status != "processing":
            raise JobCancelled("document was deleted or changed during ingestion")


async def run_ingest(ctx: JobContext) -> None:
    job, doc = _load(ctx)
    version = job.target_version

    ctx.set_stage("received")
    path = ctx.services.files.resolve_stored(doc.storage_path)
    if not Path(path).exists():
        raise JobError("parse_failed", "저장된 파일을 찾을 수 없습니다.")

    ctx.set_stage("parsing")
    try:
        parsed = await ctx.blocking(parse_pdf, path, UPLOAD_MAX_PAGES)
    except ParseError as e:
        raise JobError(e.code, str(e)) from e

    ctx.set_stage("chunking")
    chunker: Chunker = ctx.services.chunker
    spans: list[ChunkSpan] = await ctx.blocking(
        chunker.chunk_pages, [(p.page_number, p.text) for p in parsed.pages]
    )
    if not spans:
        raise JobError("no_text", "추출된 텍스트가 없습니다.")
    _store_chunks(ctx, doc.id, version, spans)

    # 임베딩·색인 단계는 M4/M5 에서 채운다 (M3 에서는 no-op).
    ctx.set_stage("embedding")
    ctx.set_stage("indexing_vector")
    ctx.set_stage("indexing_keyword")

    ctx.set_stage("activating")
    _ensure_alive(ctx, doc.id)
    _activate(ctx, doc.id, version, parsed.page_count)


def _store_chunks(ctx: JobContext, document_id: str, version: int, spans: list[ChunkSpan]) -> None:
    with ctx.services.db.session() as s:
        s.execute(delete(Chunk).where(Chunk.document_id == document_id, Chunk.index_version == version))
        s.add_all(
            Chunk(
                id=chunk_id(document_id, version, sp.page_number, sp.ordinal),
                document_id=document_id,
                index_version=version,
                page_number=sp.page_number,
                ordinal=sp.ordinal,
                text=sp.text,
                token_count=sp.token_count,
                char_start=sp.char_start,
                char_end=sp.char_end,
            )
            for sp in spans
        )
        s.commit()


def _activate(ctx: JobContext, document_id: str, version: int, page_count: int) -> None:
    """트랜잭션: ready, active_version, page_count, collections.version += 1, 이전 버전 청크 행 삭제."""
    with ctx.services.db.session() as s:
        doc = s.get(Document, document_id)
        assert doc is not None
        if doc.deleted_at is not None or doc.status != "processing":
            raise JobCancelled("document was deleted during activation")
        col = s.get(Collection, doc.collection_id)
        assert col is not None
        doc.status = "ready"
        doc.active_version = version
        doc.page_count = page_count
        doc.error_code = doc.error_message = None
        col.version += 1
        s.execute(delete(Chunk).where(Chunk.document_id == document_id, Chunk.index_version < version))
        s.commit()


async def cleanup_failed_ingest(ctx: JobContext) -> None:
    """실패·취소 시 해당 target_version 으로 들어간 청크 행을 지운다 (best-effort)."""
    try:
        with ctx.services.db.session() as s:
            job = s.get(IngestionJob, ctx.job_id)
            if job is None:
                return
            doc = s.get(Document, job.document_id)
            version = job.target_version
            active = doc.active_version if doc else 0
            if version != active:
                s.execute(
                    delete(Chunk).where(Chunk.document_id == job.document_id, Chunk.index_version == version)
                )
                s.commit()
    except Exception:  # noqa: BLE001
        log.exception("cleanup_failed", extra={"event": "cleanup_failed", "job_id": ctx.job_id})


def count_chunks(ctx: JobContext, document_id: str, version: int) -> int:
    with ctx.services.db.session() as s:
        return len(
            s.scalars(
                select(Chunk.id).where(Chunk.document_id == document_id, Chunk.index_version == version)
            ).all()
        )
