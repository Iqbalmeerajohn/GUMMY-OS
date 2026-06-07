"""FastAPI application entrypoint.

Builds the app via a factory (``create_app``) so tests and tooling can construct
isolated instances. The module-level ``app`` is what uvicorn serves:

    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.v1 import health
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.security import assert_auth_safe
from app.database.session import dispose_engine, get_sessionmaker
from app.services.embeddings.factory import get_embedding_service
from app.workers.embedding_worker import embedding_worker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle: logging, embedding worker, DB pool."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info(
        "starting %s (env=%s, version=%s)",
        settings.app_name,
        settings.app_env,
        settings.version,
    )

    # Start the background embedding worker when a database is configured.
    sessionmaker = get_sessionmaker()
    if sessionmaker is not None:
        embedding_worker.configure(
            sessionmaker=sessionmaker,
            embedding_service=get_embedding_service(),
        )
        embedding_worker.start()

    yield

    await embedding_worker.stop()
    await dispose_engine()
    logger.info("shutdown complete")


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    settings = get_settings()
    assert_auth_safe(settings)  # fail fast if dev auth bypass reaches production

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        summary="GUMMY OS backend — Phase 1 (Memory Engine).",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    # Ops probes at the root; versioned business endpoints under /api/v1.
    app.include_router(health.router)
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    """Minimal service banner pointing at docs and health."""
    settings = get_settings()
    return {
        "service": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
        "health": "/health",
    }
