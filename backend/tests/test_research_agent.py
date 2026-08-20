"""Research Agent tests (Phase 3, M8 → M8.5) — grounded analysis via the M7 seam,
plus supplemental live web search fusion (M8.5)."""

from __future__ import annotations

import uuid

import pytest

from app.schemas.agents import AgentTask, ContextPack
from app.services.agents import handlers
from app.services.agents.manifests import RESEARCH_AGENT_KEY
from app.services.llm.fake_provider import FakeLLMProvider
from app.services.search import SearchResult, search_service, set_provider


class _SettingsOn:
    web_search_enabled = True


def _task(intent: str) -> AgentTask:
    return AgentTask(
        run_id=uuid.uuid4(),
        agent_key=RESEARCH_AGENT_KEY,
        intent=intent,
        context_pack=ContextPack(
            memories=[
                {
                    "content": "User is deciding between AI and Data roles",
                    "category": "career",
                    "score": 0.7,
                }
            ]
        ),
    )


async def test_research_agent_grounds_and_uses_persona() -> None:
    llm = FakeLLMProvider(reply="Here is a side-by-side comparison.")
    result = await handlers.dispatch(
        _task("Compare AI Engineer vs Data Engineer"), llm=llm
    )
    assert result.output["reply"] == "Here is a side-by-side comparison."
    system = str(llm.calls[0]["system"])
    assert "Research Agent" in system
    assert "AI and Data roles" in system


async def test_research_agent_handles_empty_pack() -> None:
    llm = FakeLLMProvider(reply="Here is what I can analyze.")
    task = AgentTask(
        run_id=uuid.uuid4(),
        agent_key=RESEARCH_AGENT_KEY,
        intent="research the job market",
        context_pack=ContextPack(),
    )
    result = await handlers.dispatch(task, llm=llm)
    assert result.output["reply"]


async def test_research_agent_fuses_web_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_service, "get_settings", lambda: _SettingsOn())

    class _Stub:
        async def search(self, query: str, *, limit: int = 5):
            return [
                SearchResult(
                    title="Latest AI breakthroughs",
                    url="https://news.example.com/ai",
                    snippet="New model released.",
                    source="brave",
                )
            ]

    original = search_service.get_provider()
    set_provider(_Stub())
    try:
        llm = FakeLLMProvider(reply="Summary with sources.")
        # "latest" is a search cue + Research is eligible → fusion fires.
        result = await handlers.dispatch(_task("latest AI news"), llm=llm)
    finally:
        set_provider(original)

    system = str(llm.calls[0]["system"])
    assert "https://news.example.com/ai" in system
    assert "Search" in system
    sources = result.output["web_sources"]
    assert sources[0]["url"] == "https://news.example.com/ai"
    assert result.citations[0]["url"] == "https://news.example.com/ai"


async def test_research_agent_survives_search_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_service, "get_settings", lambda: _SettingsOn())

    class _Boom:
        async def search(self, query: str, *, limit: int = 5):
            raise RuntimeError("provider down")

    original = search_service.get_provider()
    set_provider(_Boom())
    try:
        llm = FakeLLMProvider(reply="Answer without live data.")
        result = await handlers.dispatch(_task("latest AI news"), llm=llm)
    finally:
        set_provider(original)

    # The reply still lands (a search outage never costs the user an answer),
    # but it no longer degrades *silently*: "latest AI news" is a question
    # about the present, so the answer says the present could not be checked.
    # Silence here let an unverified answer read as a verified one.
    reply = result.output["reply"]
    assert "Answer without live data." in reply
    assert "reliably verify current information" in reply
    # FAILED, not UNAVAILABLE: the provider exists, it just broke. Telling the
    # user to configure something that is already configured is a wrong fix.
    assert result.output["search_status"] == "failed"
    assert "couldn't reach live web search" in reply
    assert result.output["web_sources"] == []
