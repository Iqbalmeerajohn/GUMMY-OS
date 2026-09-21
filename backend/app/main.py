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
from app.core.security import assert_auth_safe, warn_if_login_is_disabled
from app.database.session import (
    dispose_engine,
    get_auth_sessionmaker,
    get_sessionmaker,
)
from app.observability import langfuse as langfuse_obs
from app.services.agents.registry import get_registry
from app.services.embeddings.factory import get_embedding_service
from app.services.llm.factory import get_llm_provider
from app.services.mcp import bridge as mcp_bridge
from app.services.search import provider as search_provider
from app.workers.automation_scheduler import automation_scheduler
from app.workers.embedding_worker import embedding_worker
from app.workers.enrichment_worker import enrichment_worker
from app.workers.telegram_worker import telegram_worker

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

    # Pre-load the local model so the user's FIRST message is answered by a warm
    # model. Without this, cold-start latency lands on exactly the message that
    # forms the user's impression of how fast Gummy is. No-op for hosted
    # providers, and never fatal.
    llm = get_llm_provider()
    warm = getattr(llm, "warm", None)
    if warm is not None:
        await warm()

    # Discover external (MCP) tools and seal the catalog. This is the single
    # moment the capability set can change; from here the process's tools are
    # fixed. Never fatal — a broken third-party server costs its own tools
    # and nothing else.
    try:
        installed = await mcp_bridge.install_configured_servers()
        if installed:
            logger.info("external tools available: %s", ", ".join(installed))
    except Exception:
        logger.exception("external tool discovery failed; continuing without it")

    # Start the background workers when a database is configured.
    sessionmaker = get_sessionmaker()
    if sessionmaker is not None:
        embedding_worker.configure(
            sessionmaker=sessionmaker,
            embedding_service=get_embedding_service(),
        )
        embedding_worker.start()
        enrichment_worker.configure(
            sessionmaker=sessionmaker,
            llm=get_llm_provider(),
            embedding_service=get_embedding_service(),
        )
        enrichment_worker.start()

        # The automation scheduler reads the automations table directly, with no
        # acting user — it runs as the system, between requests. RLS would hide
        # every row from a tenant-scoped connection, so it uses the same owner
        # connection authentication does, for the same reason: this is a
        # genuinely pre-tenant operation. Everything it then executes is scoped
        # to each automation's own user_id.
        automation_scheduler.configure(
            sessionmaker=get_auth_sessionmaker() or sessionmaker
        )
        automation_scheduler.start()

        # Telegram, if configured. Outbound polling only — no inbound port is
        # opened. The worker declines to start unless an allowlist names the
        # chats it may serve; see its own logging for exactly why it is off.
        telegram_worker.configure(
            sessionmaker=sessionmaker,
            token=settings.gummy_telegram_bot_token,
            allowed_chat_ids=settings.gummy_telegram_allowed_chat_ids,
            owner_user_id=settings.gummy_telegram_owner_user_id,
        )
        telegram_worker.start()

        # Seed the agent registry catalog (idempotent upsert of built-in
        # manifests; runs with no tenant GUC — the agents_global_seed path).
        # Best-effort: a seeding failure must not block boot.
        try:
            async with sessionmaker() as session:
                seeded = await get_registry().seed_catalog(session)
                await session.commit()
            logger.info("agent registry seeded (%d built-in agents)", seeded)
        except Exception:
            logger.exception("agent registry seeding failed; continuing")

    yield

    await telegram_worker.stop()
    await automation_scheduler.stop()
    await enrichment_worker.stop()
    await embedding_worker.stop()
    await dispose_engine()
    langfuse_obs.shutdown()  # flush buffered LLM traces (no-op when disabled)
    logger.info("shutdown complete")


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    settings = get_settings()
    # LLM/agent tracing (no-op without Langfuse keys).
    langfuse_obs.init_langfuse(settings)
    # Live web search backend (Tavily; offline Dummy default without TAVILY_API_KEY).
    search_provider.init_provider(settings)
    assert_auth_safe(settings)  # fail fast if dev auth bypass reaches production
    warn_if_login_is_disabled(settings)

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
