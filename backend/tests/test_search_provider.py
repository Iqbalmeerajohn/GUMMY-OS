"""Search provider seam tests (Phase 3, M8 → M8.5).

Pins the seam contract (Dummy default, swappable) and the Tavily backend:
payload parsing, bearer-token auth, and the guarantee that a genuine fault is
reported as ``SearchProviderError`` rather than as an empty list — a timeout
must never be readable as "the web has nothing".
"""

from __future__ import annotations

import pytest

from app.services.search import (
    DummySearchProvider,
    SearchResult,
    TavilySearchProvider,
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
        title="t", url="https://news.example.com/a", snippet="s", source="tavily"
    )
    assert r.source == "tavily"
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


async def test_tavily_provider_without_key_returns_empty() -> None:
    # No key → no network call, no raise (B10).
    assert await TavilySearchProvider("").search("ai jobs", limit=3) == []


async def test_tavily_provider_parses_payload(monkeypatch) -> None:
    sent: dict[str, object] = {}

    # Tavily's shape: a flat `results` list, snippet under `content`.
    payload = {
        "results": [
            {
                "title": "AI Engineer Jobs",
                "url": "https://example.com/ai",
                "content": "Open AI roles.",
                "score": 0.93,
            },
            {"title": "", "url": "https://example.com/skip"},  # dropped
            {
                "title": "Data Roles",
                "url": "https://data.example.com/x",
                "content": "Data jobs.",
                "score": 0.81,
            },
        ]
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

        async def post(self, url: str, **kwargs: object) -> _Resp:
            sent["url"] = url
            sent["json"] = kwargs.get("json")
            sent["headers"] = kwargs.get("headers")
            return _Resp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    results = await TavilySearchProvider("secret-key").search("ai jobs", limit=5)

    assert [r.url for r in results] == [
        "https://example.com/ai",
        "https://data.example.com/x",
    ]
    assert all(r.source == "tavily" for r in results)
    assert [r.snippet for r in results] == ["Open AI roles.", "Data jobs."]

    # The key travels as a bearer token, never in the request body: a body is
    # the thing most likely to be echoed back in an error or a debug log.
    assert sent["headers"]["Authorization"] == "Bearer secret-key"
    assert "secret-key" not in str(sent["json"])
    assert sent["json"]["query"] == "ai jobs"


async def test_tavily_provider_reports_failure_instead_of_empty(monkeypatch) -> None:
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

        async def post(self, *a, **k):
            raise RuntimeError("network down")

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _Boom)

    with pytest.raises(SearchProviderError) as excinfo:
        await TavilySearchProvider("key").search("ai jobs")

    # The message carries the exception type and nothing else: provider error
    # bodies can echo the credential back.
    assert "key" not in str(excinfo.value)
    assert "RuntimeError" in str(excinfo.value)
