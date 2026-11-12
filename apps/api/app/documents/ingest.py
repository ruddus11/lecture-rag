"""수집 파이프라인: received → parsing → chunking → embedding → indexing_vector
→ indexing_keyword → activating (설계서 5.2). 부분 성공은 없다.

실패·취소 시 이 target_version 으로 들어간 엔진 데이터와 청크 행은 best-effort 로 지운다.
재시도는 target_version 을 올려 새로 시작하므로 잔재가 있어도 원장 대조에서 걸러진다.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import delete, func, select

from app.core.config import UPLOAD_MAX_PAGES
from app.documents.chunker import Chunker, ChunkSpan, chunk_id
from app.documents.jobs import JobCancelled, JobContext, JobError
from app.documents.parser import ParseError, parse_pdf
from app.retrieval.embeddings.base import EmbeddingError
from app.retrieval.types import ChunkDoc
from app.storage.models import Chunk, Collection, Document, IngestionJob

log = logging.getLogger(__name__)


def _load(ctx: JobContext) -> tuple[IngestionJob, Document, str]:
    with ctx.services.db.session() as s:
        job = s.get(IngestionJob, ctx.job_id)
        assert job is not None
        doc = s.get(Document, job.document_id)
        assert doc is not None
        col = s.get(Collection, doc.collection_id)
        assert col is not None
        return job, doc, col.institution_id


def _ensure_alive(ctx: JobContext, document_id: str) -> None:
    with ctx.services.db.session() as s:
        doc = s.get(Document, document_id)
        if doc is None or doc.deleted_at is not None or doc.status != "processing":
            raise JobCancelled("document was deleted or changed during ingestion")


async def run_ingest(ctx: JobContext) -> None:
    services = ctx.services
    job, doc, institution_id = _load(ctx)
    version = job.target_version

    ctx.set_stage("received")
    path = services.files.resolve_stored(doc.storage_path)
    if not Path(path).exists():
        raise JobError("parse_failed", "저장된 파일을 찾을 수 없습니다.")

    ctx.set_stage("parsing")
    try:
        parsed = await ctx.blocking(parse_pdf, path, UPLOAD_MAX_PAGES)
    except ParseError as e:
        raise JobError(e.code, str(e)) from e

    ctx.set_stage("chunking")
    chunker: Chunker = services.chunker
    spans: list[ChunkSpan] = await ctx.blocking(
        chunker.chunk_pages, [(p.page_number, p.text) for p in parsed.pages]
    )
    if not spans:
        raise JobError("no_text", "추출된 텍스트가 없습니다.")
    _store_chunks(ctx, doc.id, version, spans)
    docs = [
        ChunkDoc(
            chunk_id=chunk_id(doc.id, version, sp.page_number, sp.ordinal),
            document_id=doc.id,
            collection_id=doc.collection_id,
            institution_id=institution_id,
            document_version=version,
            page_number=sp.page_number,
            ordinal=sp.ordinal,
            text=sp.text,
        )
        for sp in spans
    ]

    ctx.set_stage("embedding")
    _ensure_alive(ctx, doc.id)
    try:
        vectors = await ctx.blocking(services.doc_embedder.embed_documents, [d.text for d in docs])
    except EmbeddingError as e:
        raise JobError(e.code, str(e), retryable=True) from e
    if len(vectors) != len(docs):
        raise JobError("embedding_failed", "임베딩 수가 청크 수와 다릅니다.", retryable=True)

    ctx.set_stage("indexing_vector")
    _ensure_alive(ctx, doc.id)
    name = services.vector_collection
    try:
        await services.vector.ensure_collection(name, services.embedder.dim)
        await services.vector.upsert(name, docs, vectors)
        n = await services.vector.count_document(name, doc.id, version)
    except Exception as e:
        raise JobError("vector_index_failed", f"Qdrant 색인 실패: {type(e).__name__}", retryable=True) from e
    if n != len(docs):
        raise JobError("vector_count_mismatch", f"Qdrant {n}건, 청크 {len(docs)}건", retryable=True)

    ctx.set_stage("indexing_keyword")
    _ensure_alive(ctx, doc.id)
    await _index_keyword(ctx, doc.id, version, docs)

    ctx.set_stage("activating")
    _ensure_alive(ctx, doc.id)
    _activate(ctx, doc.id, version, parsed.page_count)
    await _purge_old_versions(ctx, doc.id, version)


async def _index_keyword(ctx: JobContext, document_id: str, version: int, docs: list[ChunkDoc]) -> None:
    kw = ctx.services.keyword
    if not hasattr(kw, "bulk_index"):  # M5 이전 어댑터
        return
    try:
        await kw.ensure_index()
        await kw.bulk_index(docs)
        n = await kw.count_document(document_id, version)
    except Exception as e:
        raise JobError(
            "keyword_index_failed", f"OpenSearch 색인 실패: {type(e).__name__}", retryable=True
        ) from e
    if n != len(docs):
        raise JobError("keyword_count_mismatch", f"OpenSearch {n}건, 청크 {len(docs)}건", retryable=True)


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
    ctx.services.invalidate_caches()


async def _purge_old_versions(ctx: JobContext, document_id: str, version: int) -> None:
    """활성화 뒤 두 엔진에서 document_id AND document_version < version 삭제 (실패는 로그만)."""
    services = ctx.services
    try:
        await services.vector.delete_document(services.vector_collection, document_id, below_version=version)
        kw = services.keyword
        if hasattr(kw, "delete_document"):
            await kw.delete_document(document_id, below_version=version)
    except Exception:  # noqa: BLE001
        log.exception("purge_old_versions_failed", extra={"event": "purge_old_versions_failed"})


async def cleanup_failed_ingest(ctx: JobContext) -> None:
    """실패·취소 시 해당 target_version 의 엔진 데이터·청크 행을 지운다 (best-effort)."""
    services = ctx.services
    try:
        with services.db.session() as s:
            job = s.get(IngestionJob, ctx.job_id)
            if job is None:
                return
            doc = s.get(Document, job.document_id)
            version = job.target_version
            document_id = job.document_id
            if doc is not None and version == doc.active_version and doc.status == "ready":
                return
            s.execute(delete(Chunk).where(Chunk.document_id == document_id, Chunk.index_version == version))
            s.commit()
        await services.vector.delete_document(services.vector_collection, document_id, version=version)
        kw = services.keyword
        if hasattr(kw, "delete_document"):
            await kw.delete_document(document_id, version=version)
    except Exception:  # noqa: BLE001
        log.exception("cleanup_failed", extra={"event": "cleanup_failed", "job_id": ctx.job_id})


def count_chunks(ctx: JobContext, document_id: str, version: int) -> int:
    with ctx.services.db.session() as s:
        return (
            s.scalar(
                select(func.count())
                .select_from(Chunk)
                .where(Chunk.document_id == document_id, Chunk.index_version == version)
            )
            or 0
        )
