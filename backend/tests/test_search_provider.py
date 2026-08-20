"""Search provider seam tests (Phase 3, M8 → M8.5).

Pins the seam contract (Dummy default, swappable) and the M8.5 Brave backend:
payload parsing, and the best-effort guarantee that any failure (no key, network
error, malformed body) degrades to ``[]`` rather than raising (B10).
"""

from __future__ import annotations

import pytest

from app.services.search import (
    BraveSearchProvider,
    DummySearchProvider,
    SearchResult,
    get_provider,
    set_provider,
)
from app.services.search.provider import SearchProviderError


async def test_dummy_provider_returns_mock_results() -> None:
    results = await DummySearchProvider().search("ai jobs", limit=3)
    assert len(results) == 3
    assert all(isinstance(r, SearchResult) for r in results)
    assert all(r.url.startswith("https://") for r in results)


async def test_dummy_provider_respects_limit_bounds() -> None:
    assert await DummySearchProvider().search("x", limit=0) == []
    assert len(await DummySearchProvider().search("x", limit=99)) == 5


def test_search_result_carries_source_and_domain() -> None:
    r = SearchResult(
        title="t", url="https://news.example.com/a", snippet="s", source="brave"
    )
    assert r.source == "brave"
    assert r.domain == "news.example.com"


def test_default_provider_is_dummy_and_swappable() -> None:
    original = get_provider()
    assert isinstance(original, DummySearchProvider)

    class _Stub:
        async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
            return []

    stub = _Stub()
    try:
        set_provider(stub)
        assert get_provider() is stub
    finally:
        set_provider(original)


async def test_brave_provider_without_key_returns_empty() -> None:
    # No key → no network call, no raise (B10).
    assert await BraveSearchProvider("").search("ai jobs", limit=3) == []


async def test_brave_provider_parses_payload(monkeypatch) -> None:
    payload = {
        "web": {
            "results": [
                {
                    "title": "AI Engineer Jobs",
                    "url": "https://example.com/ai",
                    "description": "Open AI roles.",
                },
                {"title": "", "url": "https://example.com/skip"},  # dropped
                {
                    "title": "Data Roles",
                    "url": "https://data.example.com/x",
                    "description": "Data jobs.",
                },
            ]
        }
    }

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return payload

    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def get(self, *a, **k) -> _Resp:
            return _Resp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    results = await BraveSearchProvider("key").search("ai jobs", limit=5)
    assert [r.url for r in results] == [
        "https://example.com/ai",
        "https://data.example.com/x",
    ]
    assert all(r.source == "brave" for r in results)


async def test_brave_provider_reports_failure_instead_of_empty(monkeypatch) -> None:
    """A network fault is not the same news as "the web has nothing".

    This used to return [], which made a timeout indistinguishable from a
    genuine absence of results — and the model narrated the second reading.
    """

    class _Boom:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self) -> _Boom:
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def get(self, *a, **k):
            raise RuntimeError("network down")

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _Boom)

    with pytest.raises(SearchProviderError) as excinfo:
        await BraveSearchProvider("key").search("ai jobs")

    # The message carries the exception type and nothing else: provider error
    # bodies can echo the subscription token back.
    assert "key" not in str(excinfo.value)
    assert "RuntimeError" in str(excinfo.value)
