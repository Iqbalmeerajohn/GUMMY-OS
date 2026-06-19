"""Liveness and readiness probes.

Mounted at the application root (not under ``/api/v1``) so orchestrators and load
balancers can reach them at the conventional ``/health`` paths.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.database.session import check_database
from app.schemas.health import (
    ComponentStatus,
    LivenessResponse,
    LLMHealthResponse,
    ReadinessResponse,
    WorkersHealthResponse,
    WorkerStatus,
)
from app.services.llm.factory import get_llm_provider
from app.services.llm.ollama_gateway import OllamaGateway
from app.workers.embedding_worker import embedding_worker
from app.workers.enrichment_worker import enrichment_worker

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=LivenessResponse, summary="Liveness probe")
async def liveness() -> LivenessResponse:
    """Return basic service identity — confirms the process is up."""
    settings = get_settings()
    return LivenessResponse(
        status="ok",
        service=settings.app_name,
        version=settings.version,
        environment=settings.app_env,
    )


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(response: Response) -> ReadinessResponse:
    """Report dependency health.

    Returns 503 only when a *configured* dependency is unreachable. An unset
    database (early Day 1) reports ``not_configured`` and stays ready.
    """
    db_status, db_detail = await check_database()
    components = {"database": ComponentStatus(status=db_status, detail=db_detail)}

    healthy = db_status in {"ok", "not_configured"}
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if healthy else "degraded",
        components=components,
    )


@router.get("/llm", response_model=LLMHealthResponse, summary="LLM provider probe")
async def llm_health() -> LLMHealthResponse:
    """Report the active LLM provider, its model, and reachability.

    For Ollama, ``status`` reflects a live probe of the local server. For Claude
    it reflects whether an API key is configured; the fake provider is always ok.
    """
    settings = get_settings()
    provider = settings.llm_provider.lower()

    if provider == "ollama":
        gateway = get_llm_provider()
        status_str = (
            await gateway.health()
            if isinstance(gateway, OllamaGateway)
            else "unknown"
        )
        return LLMHealthResponse(
            provider="ollama", model=settings.ollama_model, status=status_str
        )

    if provider == "fake":
        return LLMHealthResponse(provider="fake", model="fake-model", status="ok")

    status_str = "ok" if settings.anthropic_api_key else "not_configured"
    return LLMHealthResponse(
        provider="claude", model=settings.claude_model, status=status_str
    )


@router.get(
    "/workers",
    response_model=WorkersHealthResponse,
    summary="Background worker probe",
)
async def workers_health() -> WorkersHealthResponse:
    """Report whether the in-process enrichment/embedding workers are running.

    ``running`` is the live drain-task state; ``pending_jobs`` is the current
    queue depth. Use this to confirm enrichment (title + memory extraction) and
    embedding generation are actually being processed.
    """
    return WorkersHealthResponse(
        enrichment=WorkerStatus(**enrichment_worker.status()),
        embedding=WorkerStatus(**embedding_worker.status()),
    )
