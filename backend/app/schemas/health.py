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


class LLMHealthResponse(BaseModel):
    """Active LLM provider, model, and reachability."""

    provider: str
    model: str
    status: str


class WorkerStatus(BaseModel):
    """Runtime snapshot of a single background worker."""

    running: bool
    configured: bool
    pending_jobs: int


class WorkersHealthResponse(BaseModel):
    """Status of the in-process background workers (enrichment + embedding)."""

    enrichment: WorkerStatus
    embedding: WorkerStatus
