"""Application error type and FastAPI exception handlers.

Every error response shares one envelope: ``{"error": {"code", "message"}}`` —
a stable contract for the frontend and future agents.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.observability import capture_exception

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for expected, client-facing application errors."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "internal_error",
        status_code: int = 500,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def _error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message),
    )


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Report to Sentry explicitly: registering an ``Exception`` handler means
    # Starlette catches the error before the integration would, so the request
    # would otherwise never be reported. No-op when monitoring is disabled.
    capture_exception(exc, component="api")
    logger.exception("unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content=_error_body("internal_error", "An unexpected error occurred."),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the shared exception handlers to the app."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
