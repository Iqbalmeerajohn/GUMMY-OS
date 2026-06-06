"""Schemas for the health/readiness probes."""

from __future__ import annotations

from pydantic import BaseModel


class LivenessResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class ComponentStatus(BaseModel):
    status: str
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    components: dict[str, ComponentStatus]
