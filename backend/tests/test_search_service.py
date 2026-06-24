"""Search service tests (M8.5, B3/B12).

The eligibility gate (which agents + which queries may spend on live search), and
the normalize → dedupe → rank → limit pipeline over the provider seam. Best-effort
throughout: a raising provider degrades to ``[]`` (B10).
"""

from __future__ import annotations

import pytest

from app.services.search import SearchResult, search_service, set_provider


class _SettingsOn:
    web_search_enabled = True


class _SettingsOff:
    web_search_enabled = False


@pytest.fixture
def _search_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_service, "get_settings", lambda: _SettingsOn())


def test_ineligible_agent_never_searches(_search_on: None) -> None:
    assert search_service.is_search_eligible("memory", "latest AI news") is False
    assert search_service.is_search_eligible("planner", "find jobs") is False
    assert search_service.is_search_eligible(None, "latest news") is False


def test_eligible_agent_with_search_cue(_search_on: None) -> None:
    assert search_service.is_search_eligible("research", "latest AI news") is True
    assert search_service.is_search_eligible("career", "find AI jobs") is True
    assert search_service.is_search_eligible(
        "learning", "best transformer tutorials"
    ) is True


def test_eligible_agent_without_cue_is_skipped(_search_on: None) -> None:
    # Eligible agent, but the query has no recency/lookup cue.
    assert (
        search_service.is_search_eligible("research", "explain my situation")
        is False
    )


def test_year_is_a_recency_cue(_search_on: None) -> None:
    assert search_service.is_search_eligible("career", "openings in 2025") is True


def test_disabled_settings_blocks_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_service, "get_settings", lambda: _SettingsOff())
    assert search_service.is_search_eligible("research", "latest news") is False


async def test_search_normalizes_dedupes_and_limits() -> None:
    class _Stub:
        async def search(
            self, query: str, *, limit: int = 5
        ) -> list[SearchResult]:
            return [
                SearchResult("  A  ", "https://x.com/a", " s ", "stub"),
                SearchResult("A dup", "https://x.com/a/", "s", "stub"),  # dup url
                SearchResult("", "https://x.com/empty", "s", "stub"),  # dropped
                SearchResult("B", "https://y.com/b", "s", "stub"),
                SearchResult("C", "https://z.com/c", "s", "stub"),
            ]

    original = search_service.get_provider()
    set_provider(_Stub())
    try:
        results = await search_service.search("q", limit=2)
    finally:
        set_provider(original)
    assert [r.url for r in results] == ["https://x.com/a", "https://y.com/b"]
    assert results[0].title == "A"  # normalized (trimmed)


async def test_search_swallows_provider_error() -> None:
    class _Boom:
        async def search(self, query: str, *, limit: int = 5):
            raise RuntimeError("down")

    original = search_service.get_provider()
    set_provider(_Boom())
    try:
        assert await search_service.search("q") == []
    finally:
        set_provider(original)


async def test_maybe_search_gate_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_service, "get_settings", lambda: _SettingsOff())
    # Disabled → no provider call, empty result.
    assert await search_service.maybe_search("research", "latest news") == []
