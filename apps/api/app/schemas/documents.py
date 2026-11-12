from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import UtcDatetime


class UploadAccepted(BaseModel):
    document_id: str
    job_id: str
    status: str = "queued"


class DocumentOut(BaseModel):
    id: str
    collection_id: str
    filename: str
    status: str
    page_count: int | None
    chunk_count: int
    active_version: int
    error_code: str | None
    error_message: str | None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class DocumentList(BaseModel):
    items: list[DocumentOut]


class JobOut(BaseModel):
    id: str
    document_id: str
    kind: str
    status: str
    stage: str | None
    attempts: int
    max_attempts: int
    error_code: str | None
    created_at: UtcDatetime
    started_at: UtcDatetime | None
    finished_at: UtcDatetime | None


class RetryRequest(BaseModel):
    expected_version: int


class JobAccepted(BaseModel):
    job_id: str
    status: str
