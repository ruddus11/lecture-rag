"""SQLAlchemy 엔진·세션. WAL 모드, 외래키 ON, schema_version (설계서 4.1)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.storage.models import Base, SchemaVersion

SCHEMA_VERSION = 1


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        self.engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(self.engine, "connect")
        def _pragmas(dbapi_conn: Any, _: Any) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        self.sessionmaker = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)
        with self.session() as s:
            current = s.scalar(select(SchemaVersion.version))
            if current is None:
                s.add(SchemaVersion(version=SCHEMA_VERSION))
                s.commit()
            elif current != SCHEMA_VERSION:
                migrate(s, current)

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self.sessionmaker()
        try:
            yield s
        finally:
            s.close()

    def dispose(self) -> None:
        self.engine.dispose()


def migrate(s: Session, current: int) -> None:
    """스키마 변경 시 버전별 수동 마이그레이션을 여기에 추가한다."""
    raise RuntimeError(f"unsupported schema_version {current}, expected {SCHEMA_VERSION}")
