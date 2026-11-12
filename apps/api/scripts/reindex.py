"""모든 ready 문서에 ingest 작업을 다시 등록한다 (임베딩 모델 변경 후, 설계서 5.4).

docker compose exec api python -m scripts.reindex [--dry-run]

target_version = active_version + 1 로 새로 색인하므로, 완료 전까지 해당 문서는 queued/processing
상태가 되어 검색에서 빠진다. 실행 중인 API 워커가 작업을 처리한다.
"""

from __future__ import annotations

import argparse
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.storage.db import Database
from app.storage.models import Document, IngestionJob


def reindex(db: Database, dry_run: bool = False) -> list[str]:
    queued: list[str] = []
    with db.session() as s:
        for doc in s.scalars(select(Document).where(Document.status == "ready")).all():
            pending = s.scalar(
                select(IngestionJob.id).where(
                    IngestionJob.document_id == doc.id, IngestionJob.status.in_(("queued", "processing"))
                )
            )
            if pending:
                continue
            queued.append(doc.id)
            if not dry_run:
                s.add(
                    IngestionJob(
                        id=str(uuid.uuid4()),
                        document_id=doc.id,
                        kind="ingest",
                        status="queued",
                        target_version=doc.active_version + 1,
                    )
                )
                doc.status = "queued"
        if not dry_run:
            s.commit()
    return queued


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    ids = reindex(Database(get_settings().db_url), args.dry_run)
    print(f"{'would queue' if args.dry_run else 'queued'} {len(ids)} documents")
