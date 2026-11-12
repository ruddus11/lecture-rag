"""논리 삭제된 문서의 검색 인덱스·파일·청크를 순서대로 제거한다."""

from sqlalchemy import delete

from app.documents.jobs import JobContext
from app.storage.models import Chunk, Document, IngestionJob


async def run_delete(ctx: JobContext) -> None:
    services = ctx.services
    with services.db.session() as db:
        job = db.get(IngestionJob, ctx.job_id)
        assert job is not None
        doc = db.get(Document, job.document_id)
        assert doc is not None
        document_id, path = doc.id, doc.storage_path
    # 각 단계는 재실행 가능하며 중간 실패에도 논리 삭제를 되돌리지 않는다.
    ctx.set_stage("removing_indexes")
    await services.vector.delete_document(services.vector_collection, document_id)
    await services.keyword.delete_document(document_id)
    ctx.set_stage("removing_file")
    await ctx.blocking(services.files.delete, path)
    with services.db.session() as db:
        db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        doc = db.get(Document, document_id)
        assert doc is not None
        doc.status = "deleted"
        doc.error_code = doc.error_message = None
        db.commit()
    services.invalidate_caches()
