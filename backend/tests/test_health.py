"""Smoke tests for the Day 1 scaffold."""

from __future__ import annotations

from httpx import AsyncClient


async def test_liveness(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"]
    assert body["version"]


async def test_readiness(client: AsyncClient) -> None:
    resp = await client.get("/health/ready")
    # Ready whether or not a database is configured (200); only a configured but
    # unreachable DB degrades it.
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["components"]["database"]["status"] in {"ok", "not_configured"}


async def test_root(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.json()["docs"] == "/docs"
