from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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
    created_at: datetime
    updated_at: datetime


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
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RetryRequest(BaseModel):
    expected_version: int


class JobAccepted(BaseModel):
    job_id: str
    status: str
