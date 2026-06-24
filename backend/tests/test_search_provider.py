"""Search provider seam tests (Phase 3, M8 — prep for M8.5).

M8 ships only the abstraction + an offline dummy; these pin the seam contract so
real providers (Brave/Tavily) can swap in via ``set_provider`` in M8.5 without
touching callers.
"""

from __future__ import annotations

from app.services.search import (
    DummySearchProvider,
    SearchResult,
    get_provider,
    set_provider,
)


async def test_dummy_provider_returns_mock_results() -> None:
    results = await DummySearchProvider().search("ai jobs", limit=3)
    assert len(results) == 3
    assert all(isinstance(r, SearchResult) for r in results)
    assert all(r.url.startswith("https://") for r in results)


async def test_dummy_provider_respects_limit_bounds() -> None:
    assert await DummySearchProvider().search("x", limit=0) == []
    assert len(await DummySearchProvider().search("x", limit=99)) == 5


def test_default_provider_is_dummy_and_swappable() -> None:
    original = get_provider()
    assert isinstance(original, DummySearchProvider)

    class _Stub:
        async def search(
            self, query: str, *, limit: int = 5
        ) -> list[SearchResult]:
            return []

    stub = _Stub()
    try:
        set_provider(stub)
        assert get_provider() is stub
    finally:
        set_provider(original)
