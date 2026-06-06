"""Liveness and readiness probes.

Mounted at the application root (not under ``/api/v1``) so orchestrators and load
balancers can reach them at the conventional ``/health`` paths.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.database.session import check_database
from app.schemas.health import ComponentStatus, LivenessResponse, ReadinessResponse

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
