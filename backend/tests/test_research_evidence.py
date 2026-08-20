"""Evidence grounding: no live results, no claims about the present.

The failure this exists to prevent was observed live. Asked for "the latest AI
agent companies" with no search backend, Research answered "companies like
Anthropic, Anthropic, and Google's Anthropic" — one real name, duplicated, plus
one invented. Nothing in the reply told the user it had looked nothing up.

Two changes, tested here. The search layer now reports *why* it has no
evidence instead of returning a bare empty list for every reason; and a
question about the present that has no evidence attached gets an honest
sentence prepended by code, so the notice cannot be dropped by whatever the
model decided to write.

These assert behaviour and invariants rather than wording — except where the
wording is the safety property (the notice must actually say it cannot verify).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services.agents.handlers import grounding
from app.services.search import provider as search_provider
from app.services.search import search_service
from app.services.search.provider import (
    DummySearchProvider,
    SearchProviderError,
    SearchResult,
)
from app.services.search.search_service import SearchStatus


class _SettingsOn:
    """Settings with live search switched on (the provider decides the rest)."""

    web_search_enabled = True


@pytest.fixture
def live_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_service, "get_settings", lambda: _SettingsOn())


@pytest.fixture
def restore_provider() -> Any:
    original = search_provider.get_provider()
    yield
    search_provider.set_provider(original)


def _hit(n: int, url: str | None = None) -> SearchResult:
    return SearchResult(
        title=f"Result {n}",
        url=url or f"https://example.com/{n}",
        snippet=f"Snippet {n}",
        source="brave",
    )


class _Provider:
    """A stand-in backend whose behaviour each test chooses."""

    def __init__(self, results: list[SearchResult] | None = None, boom: bool = False):
        self._results = results or []
        self._boom = boom
        self.queries: list[str] = []

    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        self.queries.append(query)
        if self._boom:
            raise SearchProviderError("provider exploded")
        return self._results[:limit]


# ── 1-3. Freshness: what genuinely needs current evidence ───────────────────


@pytest.mark.parametrize(
    "query",
    [
        "What is RAG?",
        "Explain how transformers work",
        "Compare RAG and fine-tuning",
        "What are the best practices for prompt engineering",
        "Teach me linear algebra",
        "How do I write a good resume",
    ],
)
def test_timeless_questions_do_not_require_evidence(query: str) -> None:
    """These are answerable from a model. Demanding search for them would
    refuse ordinary teaching questions — the opposite failure."""
    assert not search_service.requires_fresh_evidence(query)


@pytest.mark.parametrize(
    "query",
    [
        "What are the latest developments in AI agents?",
        "What's new in LangGraph",
        "Recent AI news",
        "What is OpenAI currently working on",
        "AI agent trends this month",
        "What happened today in AI",
        "Best AI frameworks in 2026",
    ],
)
def test_current_information_questions_require_evidence(query: str) -> None:
    assert search_service.requires_fresh_evidence(query)


@pytest.mark.parametrize(
    "query",
    [
        "Find current AI/ML fresher jobs",
        "Who is hiring ML engineers",
        "What are current job openings at Anthropic",
        "What is the price of the OpenAI API",
        "What version of Python is newest",
    ],
)
def test_volatile_subjects_require_evidence(query: str) -> None:
    """No time word, but the answer decays fast enough that stating it from
    model memory is still a claim about the present."""
    assert search_service.requires_fresh_evidence(query)


# ── 4-7. The four outcomes stay distinct ────────────────────────────────────


async def test_missing_provider_key_is_unavailable(
    live_settings: None, restore_provider: None
) -> None:
    search_provider.set_provider(DummySearchProvider())

    outcome = await search_service.search_outcome("latest ai news")

    assert outcome.status is SearchStatus.UNAVAILABLE
    assert outcome.results == []
    assert not outcome.has_evidence


async def test_provider_failure_is_failed_not_empty(
    live_settings: None, restore_provider: None
) -> None:
    search_provider.set_provider(_Provider(boom=True))

    outcome = await search_service.search_outcome("latest ai news")

    assert outcome.status is SearchStatus.FAILED
    assert not outcome.has_evidence


async def test_zero_hits_is_no_results(
    live_settings: None, restore_provider: None
) -> None:
    search_provider.set_provider(_Provider(results=[]))

    outcome = await search_service.search_outcome("latest ai news")

    assert outcome.status is SearchStatus.NO_RESULTS
    assert not outcome.has_evidence


async def test_real_hits_are_available(
    live_settings: None, restore_provider: None
) -> None:
    search_provider.set_provider(_Provider(results=[_hit(1), _hit(2)]))

    outcome = await search_service.search_outcome("latest ai news")

    assert outcome.status is SearchStatus.AVAILABLE
    assert outcome.has_evidence
    assert len(outcome.results) == 2


async def test_the_offline_placeholder_never_counts_as_evidence(
    live_settings: None, restore_provider: None
) -> None:
    """The original bug: mock rows were reported as a successful search and
    the model relayed them to the user as findings."""
    search_provider.set_provider(DummySearchProvider())

    outcome = await search_service.search_outcome("anything")

    assert not outcome.has_evidence
    assert outcome.results == []
    assert "example.com" not in str(outcome.results)


# ── 8-9. Structured results, deduplicated ───────────────────────────────────


async def test_results_carry_title_url_and_snippet(
    live_settings: None, restore_provider: None
) -> None:
    search_provider.set_provider(_Provider(results=[_hit(1)]))

    outcome = await search_service.search_outcome("latest ai news")

    (result,) = outcome.results
    assert result.title and result.url and result.snippet
    assert result.source == "brave"
    assert result.domain == "example.com"


async def test_duplicate_urls_are_removed(
    live_settings: None, restore_provider: None
) -> None:
    dupes = [
        _hit(1, "https://example.com/a"),
        _hit(2, "https://example.com/a/"),  # trailing slash only
        _hit(3, "https://example.com/b"),
    ]
    search_provider.set_provider(_Provider(results=dupes))

    outcome = await search_service.search_outcome("latest ai news", limit=10)

    urls = [r.url for r in outcome.results]
    assert len(urls) == 2
    assert "https://example.com/b" in urls


async def test_a_result_missing_a_url_is_dropped(
    live_settings: None, restore_provider: None
) -> None:
    partial = [SearchResult(title="No link", url="", snippet="x", source="brave")]
    search_provider.set_provider(_Provider(results=partial))

    outcome = await search_service.search_outcome("latest ai news")

    assert outcome.status is SearchStatus.NO_RESULTS


# ── 10-11. The agent gets the evidence, or an honest notice ─────────────────


def _prepared(status: str, evidence_missing: bool) -> grounding.PreparedTurn:
    return grounding.PreparedTurn(
        system="",
        messages=[],
        memories_used=0,
        evidence_missing=evidence_missing,
        search_status=status,
    )


class _Response:
    def __init__(self, text: str):
        self.text = text
        self.model = "fake"
        self.input_tokens = 1
        self.output_tokens = 1


@pytest.mark.parametrize(
    ("status", "must_contain"),
    [
        ("unavailable", "isn't configured"),
        ("failed", "couldn't reach live web search"),
        ("no_results", "returned nothing"),
    ],
)
def test_each_reason_gets_its_own_honest_notice(status: str, must_contain: str) -> None:
    """ "Not configured" is a setup step; "couldn't reach it" is worth
    retrying; "found nothing" is not about us at all. One message for all
    three would tell the user to fix something that isn't broken."""
    result = grounding.finish(
        _prepared(status, evidence_missing=True),
        _Response("Here are the latest releases."),
    )

    reply = result.output["reply"]
    assert must_contain in reply
    assert "reliably verify current information" in reply
    assert "Here are the latest releases." in reply


def test_no_notice_is_added_when_evidence_was_available() -> None:
    """An ordinary answer must not be decorated with a disclaimer it doesn't
    need — that trains the user to ignore the disclaimer."""
    result = grounding.finish(
        _prepared("available", evidence_missing=False),
        _Response("RAG retrieves documents and conditions generation on them."),
    )

    assert result.output["reply"].startswith("RAG retrieves")
    assert "verify" not in result.output["reply"]


def test_the_notice_is_not_duplicated_when_the_model_already_said_it() -> None:
    already = (
        "I can't reliably verify current information right now, but "
        "here's the shape of it."
    )

    result = grounding.finish(
        _prepared("unavailable", evidence_missing=True), _Response(already)
    )

    assert result.output["reply"] == already


def test_the_directive_tells_the_model_what_to_write_not_only_what_to_avoid() -> None:
    directive = grounding.NO_EVIDENCE_DIRECTIVE

    assert "Open by saying you cannot verify" in directive
    assert "Do NOT state current facts" in directive
    assert "fabrication even if it happens to be right" in directive


def test_the_search_status_is_reported_on_the_result() -> None:
    """So a caller (or a trace) can tell evidence-backed answers apart from
    unverified ones without re-deriving it."""
    result = grounding.finish(
        _prepared("failed", evidence_missing=True), _Response("x")
    )

    assert result.output["search_status"] == "failed"
    assert result.output["evidence_missing"] is True


# ── 12. Career may not invent openings ──────────────────────────────────────


def test_career_persona_forbids_inventing_current_openings() -> None:
    """The most expensive fabrication this product can make: the user applies
    to a job that was never there."""
    from app.services.agents.prompts import career_agent_prompt

    persona = career_agent_prompt.build_persona("find me jobs", "")

    assert "NEVER invent current openings" in persona
    assert "appears in live search results" in persona
    # ...and it still has plenty to offer without live data.
    assert "work on the resume" in persona


def test_research_persona_forbids_naming_specifics_without_search() -> None:
    from app.services.agents.prompts import research_agent_prompt

    persona = research_agent_prompt.build_persona("anything", "")

    assert "you cannot look anything up" in persona
    assert "do NOT name specific companies" in persona


# ── 13-14. Eligibility gating is unchanged for non-search agents ────────────


@pytest.mark.parametrize("agent", ["general", "memory", "planner", "automation"])
def test_non_search_agents_never_reach_the_network(
    agent: str, live_settings: None, restore_provider: None
) -> None:
    probe = _Provider(results=[_hit(1)])
    search_provider.set_provider(probe)

    assert not search_service.is_search_eligible(agent, "latest ai news")


def test_search_agents_are_eligible_for_search_worthy_queries(
    live_settings: None,
) -> None:
    for agent in ("research", "career", "learning"):
        assert search_service.is_search_eligible(agent, "latest ai news")


def test_search_is_off_entirely_when_settings_disable_it() -> None:
    class _Off:
        web_search_enabled = False

    import app.services.search.search_service as svc

    original = svc.get_settings
    svc.get_settings = lambda: _Off()  # type: ignore[assignment]
    try:
        assert not svc.is_search_eligible("research", "latest ai news")
    finally:
        svc.get_settings = original  # type: ignore[assignment]


async def test_an_ineligible_fresh_question_reports_unavailable(
    restore_provider: None,
) -> None:
    """Settings off + a question about the present: the user is owed the
    reason, not an empty list."""
    outcome = await search_service.maybe_search_outcome(
        "research", "what are the latest AI agent releases"
    )

    assert outcome.status is SearchStatus.UNAVAILABLE


async def test_an_ineligible_timeless_question_is_simply_no_results() -> None:
    """Not every search-free turn is a failure — most questions never needed
    one, and telling the user search is unavailable would be noise."""
    outcome = await search_service.maybe_search_outcome("research", "what is RAG")

    assert outcome.status is SearchStatus.NO_RESULTS


# ── 20. The key never leaks ─────────────────────────────────────────────────


async def test_a_provider_failure_message_never_carries_the_api_key() -> None:
    """Provider error bodies sometimes echo the subscription token back."""
    import httpx

    secret = "brave-secret-key-do-not-log"

    class _Boom:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def get(self, *a: Any, **k: Any) -> Any:
            raise RuntimeError(f"401 unauthorized for token {secret}")

    original = httpx.AsyncClient
    httpx.AsyncClient = _Boom  # type: ignore[misc, assignment]
    try:
        with pytest.raises(SearchProviderError) as excinfo:
            await search_provider.BraveSearchProvider(secret).search("x")
    finally:
        httpx.AsyncClient = original  # type: ignore[misc]

    assert secret not in str(excinfo.value)


async def test_the_search_outcome_never_carries_the_api_key(
    live_settings: None, restore_provider: None
) -> None:
    secret = "brave-secret-key-do-not-log"
    search_provider.set_provider(search_provider.BraveSearchProvider(secret))

    outcome = await search_service.search_outcome("latest ai news")

    assert secret not in repr(outcome)


def test_settings_never_expose_the_key_through_the_capability_block() -> None:
    """The capability block is user-facing text assembled from settings."""
    from app.services.agents.prompts import identity

    block = identity.capability_block()

    assert "BRAVE_API_KEY" not in block
    assert "api key" not in block.lower()


# ── Tenant isolation is unaffected by search ────────────────────────────────


async def test_search_is_not_scoped_per_user_but_carries_no_user_data(
    live_settings: None, restore_provider: None
) -> None:
    """Search queries are the user's words; nothing else about them should
    reach the provider."""
    probe = _Provider(results=[_hit(1)])
    search_provider.set_provider(probe)

    await search_service.maybe_search_outcome(
        "research", "latest ai news", user_id=uuid.uuid4()
    )

    assert probe.queries == ["latest ai news"]


# ── 18. Parallel synthesis must not lose the caveat ─────────────────────────


async def test_synthesis_restores_a_dropped_unverified_notice() -> None:
    """Observed live in a Career+Research parallel turn: Research correctly
    reported that it could not verify current information, and the synthesis
    summarised the Career half and dropped the caveat. Nothing in the answer
    was false — but the user was left believing the whole question had been
    answered."""
    from app.schemas.agents import AgentResult, CostInfo
    from app.services.agents import synthesis

    class _Summariser:
        async def generate(self, **_: object) -> object:
            class _R:
                text = (
                    "To find AI/ML jobs, tailor your resume and use targeted "
                    "search terms, then review it together."
                )

            return _R()

    results = [
        (
            "career",
            AgentResult(
                agent_key="career",
                output={"reply": "resume advice", "evidence_missing": False},
                cost=CostInfo(tokens=0, usd=0.0),
            ),
        ),
        (
            "research",
            AgentResult(
                agent_key="research",
                output={
                    "reply": "Live web search isn't configured...",
                    "evidence_missing": True,
                    "search_status": "unavailable",
                },
                cost=CostInfo(tokens=0, usd=0.0),
            ),
        ),
    ]

    reply = await synthesis.synthesize_parallel(results, [], llm=_Summariser())  # type: ignore[arg-type]

    assert "reliably verify current information" in reply
    assert "tailor your resume" in reply


async def test_synthesis_does_not_duplicate_a_notice_it_kept() -> None:
    from app.schemas.agents import AgentResult, CostInfo
    from app.services.agents import synthesis

    class _Faithful:
        async def generate(self, **_: object) -> object:
            class _R:
                text = (
                    "Live web search isn't configured on this GUMMY instance, "
                    "so I can't reliably verify current information. Here is "
                    "what I can still help with."
                )

            return _R()

    results = [
        (
            "research",
            AgentResult(
                agent_key="research",
                output={
                    "reply": "x",
                    "evidence_missing": True,
                    "search_status": "unavailable",
                },
                cost=CostInfo(tokens=0, usd=0.0),
            ),
        )
    ]

    reply = await synthesis.synthesize_parallel(results, [], llm=_Faithful())  # type: ignore[arg-type]

    assert reply.lower().count("reliably verify") == 1
