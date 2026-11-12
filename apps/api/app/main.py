"""FastAPI 앱 생성, 라우터 등록, lifespan."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, collections, documents, health, jobs, search
from app.container import Services, build_services
from app.core.config import CHUNKER_VERSION, PARSER_VERSION, Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import RequestContextMiddleware, setup_logging
from app.documents.jobs import JobRunner
from app.storage.models import IndexProfile
from app.storage.seed import seed_from_files

API_PREFIX = "/api/v1"
log = logging.getLogger(__name__)


async def _warm_up(services: Services) -> None:
    """임베딩 모델 적재 → 색인 프로필 기록 → Qdrant 컬렉션 준비. 실패해도 기동은 계속한다(ready 가 알린다)."""
    try:
        await asyncio.to_thread(services.embedder.load)
        register_index_profile(services)
        await services.vector.ensure_collection(services.vector_collection, services.embedder.dim)
    except Exception as e:  # noqa: BLE001
        log.warning("warm_up_failed", extra={"event": "warm_up_failed", "error": repr(e)[:300]})
    try:
        await services.keyword.ensure_index()
    except Exception as e:  # noqa: BLE001
        log.warning("warm_up_failed", extra={"event": "warm_up_failed", "error": repr(e)[:300]})


def register_index_profile(services: Services) -> None:
    with services.db.session() as s:
        pid = services.index_profile_id
        if s.get(IndexProfile, pid) is None:
            s.add(
                IndexProfile(
                    id=pid,
                    embedding_provider=services.embedder.name,
                    embedding_model=services.embedder.model,
                    dim=services.embedder.dim,
                    chunker_version=CHUNKER_VERSION,
                    parser_version=PARSER_VERSION,
                    qdrant_collection=services.vector_collection,
                    opensearch_index=services.keyword_index,
                )
            )
            s.commit()


def create_app(
    settings: Settings | None = None,
    services_factory: Callable[[Settings], Services] = build_services,
    start_worker: bool = True,
) -> FastAPI:
    """start_worker=False 는 테스트용: 워커 태스크를 띄우지 않고 runner.drain() 으로 직접 처리한다."""
    settings = settings or get_settings()
    setup_logging(settings.log_level, settings.secret_values())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        services = services_factory(settings)
        services.db.create_all()
        if settings.seed_on_start:
            seed_from_files(services.db, settings.institutions_file, settings.users_file)
        services.files.ensure_dirs()
        app.state.services = services
        runner = services.runner = JobRunner(services)
        runner.recover()
        if start_worker:
            runner.start()
        loader = asyncio.create_task(_warm_up(services))
        try:
            yield
        finally:
            loader.cancel()
            await runner.stop()
            for c in (services.vector, services.keyword):
                close = getattr(c, "close", None)
                if close:
                    await close()
            services.db.dispose()

    docs = settings.expose_docs
    app = FastAPI(
        title="lecture-rag-search",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs" if docs else None,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs else None,
        redoc_url=None,
    )
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Range", "X-Request-Id"],
        expose_headers=["X-Request-Id", "Retry-After", "Content-Range"],
    )
    app.add_middleware(RequestContextMiddleware)
    for r in (health.router, auth.router, collections.router, documents.router, jobs.router, search.router):
        app.include_router(r, prefix=API_PREFIX)
    return app


app = create_app()
