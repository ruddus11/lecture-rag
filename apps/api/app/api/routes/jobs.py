from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.core.errors import AppError
from app.core.scope import check_document_access
from app.schemas.documents import JobOut
from app.storage.models import IngestionJob, User

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> JobOut:
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise AppError(404, "job_not_found", "요청한 작업을 찾을 수 없습니다.")
    try:
        check_document_access(db, user, job.document_id)
    except AppError:
        raise AppError(404, "job_not_found", "요청한 작업을 찾을 수 없습니다.") from None
    return JobOut.model_validate(job, from_attributes=True)
