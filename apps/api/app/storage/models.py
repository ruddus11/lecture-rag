"""SQLite 원장 ORM 모델 (설계서 4.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)


class Institution(Base):
    __tablename__ = "institutions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('student','admin')", name="ck_users_role"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"))
    role: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("institution_id", "slug", name="uq_collections_inst_slug"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"))
    slug: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    allowed_roles: Mapped[list[str]] = mapped_column(JSON)
    search_profile: Mapped[dict[str, Any]] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


DOCUMENT_STATUSES = ("queued", "processing", "ready", "failed", "deleting", "deleted")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','processing','ready','failed','deleting','deleted')",
            name="ck_documents_status",
        ),
        Index(
            "uq_documents_live_sha",
            "collection_id",
            "sha256",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id"))
    original_filename: Mapped[str] = mapped_column(String)
    sha256: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="queued")
    active_version: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(String)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


JOB_STAGES = (
    "received",
    "parsing",
    "chunking",
    "embedding",
    "indexing_vector",
    "indexing_keyword",
    "activating",
    "removing_indexes",
    "removing_file",
)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('ingest','delete')", name="ck_jobs_kind"),
        CheckConstraint("status IN ('queued','processing','succeeded','failed')", name="ck_jobs_status"),
        Index("ix_jobs_status_created", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="queued")
    stage: Mapped[str | None] = mapped_column(String, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    target_version: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "index_version", "page_number", "ordinal", name="uq_chunks_doc_ver_page_ord"
        ),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    index_version: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int] = mapped_column(Integer)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)


class IndexProfile(Base):
    __tablename__ = "index_profiles"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    embedding_provider: Mapped[str] = mapped_column(String)
    embedding_model: Mapped[str] = mapped_column(String)
    dim: Mapped[int] = mapped_column(Integer)
    chunker_version: Mapped[str] = mapped_column(String)
    parser_version: Mapped[str] = mapped_column(String)
    qdrant_collection: Mapped[str] = mapped_column(String)
    opensearch_index: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (PrimaryKeyConstraint("key", "user_id"),)
    key: Mapped[str] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(String)
    document_id: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QueryLog(Base):
    __tablename__ = "query_logs"
    request_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String)
    institution_id: Mapped[str] = mapped_column(String)
    mode: Mapped[str] = mapped_column(String)
    collection_ids: Mapped[list[str]] = mapped_column(JSON)
    timings_ms: Mapped[dict[str, Any]] = mapped_column(JSON)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    cache_status: Mapped[str] = mapped_column(String)
    abstained: Mapped[int] = mapped_column(Integer, default=0)
    degraded: Mapped[int] = mapped_column(Integer, default=0)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # LOG_QUERY_TEXT=true 일 때만
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
