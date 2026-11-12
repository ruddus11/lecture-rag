"""문서 업로드·조회 (설계서 5.2 received 단계, 8.2)."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Header, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db, get_services, require_admin
from app.container import Services
from app.core.config import UPLOAD_MAX_MB
from app.core.errors import AppError, document_not_found
from app.core.scope import check_collection_access, check_document_access
from app.schemas.documents import DocumentList, DocumentOut, UploadAccepted
from app.storage.files import FileTooLarge
from app.storage.models import Chunk, Document, IdempotencyKey, IngestionJob, User, utcnow

router = APIRouter(tags=["documents"])
log = logging.getLogger(__name__)

IDEMPOTENCY_TTL = timedelta(hours=24)
DocStatus = Literal["queued", "processing", "ready", "failed", "deleting"]


def document_out(db: Session, doc: Document) -> DocumentOut:
    chunk_count = (
        db.scalar(
            select(func.count())
            .select_from(Chunk)
            .where(Chunk.document_id == doc.id, Chunk.index_version == doc.active_version)
        )
        or 0
    )
    return DocumentOut(
        id=doc.id,
        collection_id=doc.collection_id,
        filename=doc.original_filename,
        status=doc.status,
        page_count=doc.page_count,
        chunk_count=chunk_count,
        active_version=doc.active_version,
        error_code=doc.error_code,
        error_message=doc.error_message,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _idempotent_replay(db: Session, key: str, user: User) -> UploadAccepted | None:
    """같은 사용자·키의 24시간 내 요청이면 처음 응답과 같은 본문을 돌려준다."""
    row = db.get(IdempotencyKey, (key, user.id))
    if row is None:
        return None
    created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=utcnow().tzinfo)
    if utcnow() - created > IDEMPOTENCY_TTL:
        db.delete(row)
        db.commit()
        return None
    job_id = db.scalar(
        select(IngestionJob.id)
        .where(IngestionJob.document_id == row.document_id, IngestionJob.kind == "ingest")
        .order_by(IngestionJob.created_at)
        .limit(1)
    )
    return UploadAccepted(document_id=row.document_id, job_id=job_id or "", status="queued")


@router.post(
    "/collections/{collection_id}/documents",
    status_code=202,
    response_model=UploadAccepted,
    description=f"PDF 업로드(최대 {UPLOAD_MAX_MB}MB). 같은 Idempotency-Key 재요청은 200 과 같은 본문.",
)
async def upload_document(
    collection_id: str,
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> UploadAccepted | JSONResponse:
    services.ratelimiter.check(user.id, "upload")
    col = check_collection_access(db, user, collection_id)

    if idempotency_key:
        db.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < utcnow() - IDEMPOTENCY_TTL))
        db.commit()
        replay = _idempotent_replay(db, idempotency_key, user)
        if replay is not None:
            return JSONResponse(replay.model_dump(), status_code=200)

    filename = (file.filename or "upload.pdf").replace("/", "_").replace("\\", "_")[:255]
    if not filename.lower().endswith(".pdf"):
        raise AppError(415, "unsupported_media_type", "PDF 파일만 업로드할 수 있습니다.")
    files = services.files
    try:
        tmp, sha256, size, head = files.save_temp(file.file, UPLOAD_MAX_MB * 1024 * 1024)
    except FileTooLarge:
        raise AppError(413, "file_too_large", f"파일 크기가 {UPLOAD_MAX_MB}MB를 넘습니다.") from None
    if not head.startswith(b"%PDF-"):
        files.discard(tmp)
        raise AppError(415, "unsupported_media_type", "PDF 형식이 아닙니다.")

    dup = db.scalar(
        select(Document.id).where(
            Document.collection_id == col.id, Document.sha256 == sha256, Document.deleted_at.is_(None)
        )
    )
    if dup:
        files.discard(tmp)
        raise AppError(
            409, "duplicate_document", "같은 파일이 이미 이 컬렉션에 있습니다.", details={"document_id": dup}
        )

    doc_id = str(uuid.uuid4())
    path = files.commit(tmp, doc_id)
    doc = Document(
        id=doc_id,
        collection_id=col.id,
        original_filename=filename,
        sha256=sha256,
        size_bytes=size,
        status="queued",
        active_version=0,
        storage_path=str(path),
        created_by=user.id,
    )
    job = IngestionJob(
        id=str(uuid.uuid4()), document_id=doc_id, kind="ingest", status="queued", target_version=1
    )
    db.add(doc)
    db.flush()
    db.add(job)
    if idempotency_key:
        db.add(IdempotencyKey(key=idempotency_key, user_id=user.id, document_id=doc_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        files.delete(str(path))
        raise AppError(409, "duplicate_document", "같은 파일이 이미 이 컬렉션에 있습니다.") from None
    log.info(
        "document_received",
        extra={"event": "document_received", "document_id": doc_id, "job_id": job.id, "size_bytes": size},
    )
    if services.runner:
        services.runner.notify()
    return UploadAccepted(document_id=doc_id, job_id=job.id, status="queued")


@router.get("/collections/{collection_id}/documents", response_model=DocumentList)
async def list_documents(
    collection_id: str,
    status: DocStatus | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> DocumentList:
    col = check_collection_access(db, user, collection_id)
    q = select(Document).where(Document.collection_id == col.id, Document.status != "deleted")
    if status:
        q = q.where(Document.status == status)
    docs = db.scalars(q.order_by(Document.created_at.desc())).all()
    return DocumentList(items=[document_out(db, d) for d in docs])


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> DocumentOut:
    return document_out(db, check_document_access(db, user, document_id))


_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """단일 범위만 지원한다. 형식이 틀리면 None(전체 200), 만족 불가면 416."""
    if not header:
        return None
    m = _RANGE.match(header.strip())
    if not m or (m.group(1) == "" and m.group(2) == ""):
        return None
    if m.group(1) == "":  # bytes=-N (끝에서 N 바이트)
        n = int(m.group(2))
        if n == 0:
            raise AppError(416, "range_not_satisfiable", "요청한 범위를 만족할 수 없습니다.")
        return max(0, size - n), size - 1
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else size - 1
    if start >= size or end < start:
        raise AppError(
            416,
            "range_not_satisfiable",
            "요청한 범위를 만족할 수 없습니다.",
            headers={"Content-Range": f"bytes */{size}"},
        )
    return start, min(end, size - 1)


@router.get("/documents/{document_id}/file", response_class=StreamingResponse)
async def get_document_file(
    document_id: str,
    range_header: str | None = Header(default=None, alias="Range"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> StreamingResponse:
    """요청마다 scope 를 다시 계산하고 ready 문서만 준다 (설계서 9.2 규칙 6)."""
    doc = check_document_access(db, user, document_id, include_deleting=False)
    if doc.status != "ready":
        raise document_not_found()
    try:
        path = services.files.resolve_stored(doc.storage_path)
        size = path.stat().st_size
    except (ValueError, OSError):
        raise document_not_found() from None
    quoted = quote(doc.original_filename, safe="")
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"inline; filename*=UTF-8''{quoted}",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    rng = _parse_range(range_header, size)
    start, end = rng if rng else (0, size - 1)
    headers["Content-Length"] = str(end - start + 1)
    status = 200
    if rng:
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        services.files.open_range(doc.storage_path, start, end),
        status_code=status,
        media_type="application/pdf",
        headers=headers,
    )
