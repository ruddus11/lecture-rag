"""FastAPI 앱 생성, 라우터 등록, lifespan."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health
from app.container import Services, build_services
from app.core.config import Settings, get_settings

API_PREFIX = "/api/v1"
log = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    services_factory: Callable[[Settings], Services] = build_services,
) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        services = services_factory(settings)
        app.state.services = services
        loader = asyncio.create_task(asyncio.to_thread(services.embedder.load))
        try:
            yield
        finally:
            loader.cancel()
            for c in (services.vector, services.keyword):
                close = getattr(c, "close", None)
                if close:
                    await close()

    docs = settings.expose_docs
    app = FastAPI(
        title="lecture-rag-search",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs" if docs else None,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs else None,
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Range", "X-Request-Id"],
        expose_headers=["X-Request-Id", "Retry-After", "Content-Range"],
    )
    app.include_router(health.router, prefix=API_PREFIX)
    return app


app = create_app()
