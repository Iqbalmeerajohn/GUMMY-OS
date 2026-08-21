"""Regressions for the auth + search UX pass.

Four defects, each found by running the thing rather than reading it:

* an expired Google OAuth ``state`` returned a raw JSON error blob to a
  browser, even though the login page already had the message for it;
* the ``web_search`` tool handed the model the provider name and an
  ``untrusted`` flag, which it read out to the user verbatim;
* the knowledge block labelled hits ``[search:<provider>]``, putting the vendor
  in the model's context a second time;
* Career's invention ban covered vacancies but not the salary, location or
  deadline attached to one.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.services.agents.prompts import career_agent_prompt, research_agent_prompt
from app.services.agents.tools import web_search
from app.services.knowledge import knowledge_context_builder as builder
from app.services.knowledge.knowledge_retrieval_service import (
    SOURCE_SEARCH,
    KnowledgeItem,
)
from app.services.search import provider as search_provider
from app.services.search.provider import SearchResult

# ── Google OAuth: a browser gets a page, not JSON ───────────────────────────


@pytest.mark.parametrize(
    ("query", "expected_error"),
    [
        ("", "oauth_state_missing"),
        ("code=abc&state=not-a-real-jwt", "oauth_state_invalid"),
    ],
)
async def test_a_bad_oauth_state_redirects_instead_of_returning_json(
    api_client: AsyncClient, query: str, expected_error: str
) -> None:
    """An expired state is a normal user event — they lingered on Google's
    consent screen — and this URL is opened by Google's redirect, so whatever
    it returns is what the browser renders. It used to render
    ``{"error": {...}}``.

    The rejection itself is unchanged; only the reporting is.
    """
    response = await api_client.get(
        f"/api/v1/auth/google/callback?{query}", follow_redirects=False
    )

    assert response.status_code in (302, 307)
    location = response.headers["location"]
    assert "/login?error=" in location
    assert expected_error in location
    # Critically: no session was minted.
    assert "access_token" not in location


async def test_an_explicit_google_denial_still_redirects(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get(
        "/api/v1/auth/google/callback?error=access_denied&state=x",
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    assert "error=access_denied" in response.headers["location"]


def test_the_frontend_has_a_message_for_every_redirect_reason() -> None:
    """The backend's error codes and the login page's message map have to
    agree — a code with no message renders as a bare slug."""
    from pathlib import Path

    login = Path(__file__).resolve().parents[2] / (
        "frontend/src/app/(auth)/login/page.tsx"
    )
    source = login.read_text(encoding="utf-8")

    for code in (
        "access_denied",
        "oauth_state_invalid",
        "oauth_state_missing",
        "missing_code",
    ):
        assert code in source, f"login page has no message for {code!r}"


# ── The model must not be handed machinery ──────────────────────────────────


async def test_the_search_tool_payload_carries_only_citable_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Observed live: "These listings are pulled from the Tavily platform,
    which is considered untrusted." The model had read the provider name and
    the ``untrusted`` marker straight out of the tool result."""
    monkeypatch.setattr(search_provider, "is_live", lambda: True)

    async def _fake_search(query: str, *, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title="AI Engineer Jobs",
                url="https://jobs.example.com/ai",
                snippet="Open roles.",
                source="tavily",
            )
        ]

    monkeypatch.setattr(web_search.search_service, "search", _fake_search)

    result = await web_search.execute(None, {"query": "ai jobs"})  # type: ignore[arg-type]

    assert "untrusted" not in result
    (hit,) = result["results"]
    assert set(hit) == {"title", "url", "domain", "snippet"}
    assert hit["domain"] == "jobs.example.com"
    # The vendor name is nowhere in what the model will read.
    assert "tavily" not in str(result).lower()


def test_the_knowledge_block_labels_hits_web_not_by_vendor() -> None:
    item = KnowledgeItem(
        source=SOURCE_SEARCH,
        item_id="https://news.example.com/a",
        content="Headline — snippet",
        label="Headline",
        source_score=0.0,
        metadata={
            "title": "Headline",
            "url": "https://news.example.com/a",
            "domain": "news.example.com",
            "snippet": "snippet",
            "provider": "tavily",
            "order": 0,
        },
    )

    rendered = builder._render_search(item)

    assert rendered.startswith("- [web] Headline")
    assert "news.example.com" in rendered  # the part a reader should see
    assert "tavily" not in rendered.lower()


# ── Answer quality rules ────────────────────────────────────────────────────


def test_research_must_separate_sourced_fact_from_its_own_reasoning() -> None:
    """The subtle failure: a source says one thing, the model generalises it,
    and the citation makes the generalisation look sourced too."""
    persona = research_agent_prompt.build_persona("x", "")

    assert "Separate what the sources actually say" in persona
    assert "could not be verified" in persona


@pytest.mark.parametrize("persona_module", [research_agent_prompt, career_agent_prompt])
def test_neither_agent_may_write_internal_result_identifiers(
    persona_module: Any,
) -> None:
    """Users were shown "[Search result 1]" — an internal handle that tells
    them nothing and looks like a bug."""
    persona = persona_module.build_persona("x", "")

    assert "Search result 1" in persona  # named so it can be forbidden
    assert "internal identifiers" in persona


def test_career_may_not_invent_the_details_attached_to_a_vacancy() -> None:
    """The ban covered the opening itself but not the salary, city or closing
    date hung off it — which are exactly the fields a listing tends to omit and
    a model tends to supply."""
    persona = career_agent_prompt.build_persona("find me jobs", "")

    for field in ("salary figure", "location", "deadline"):
        assert field in persona, f"{field} is not covered by the invention ban"
    assert "only as that source states it" in persona
    assert "say that detail is not listed" in persona


# ── SMTP configuration and failure handling ─────────────────────────────────


def test_smtp_mode_requires_a_host_and_says_so() -> None:
    """Silently falling back to console would make a deployment that meant to
    send email log links forever while looking like it worked."""
    from app.services.auth import mailer

    settings = get_settings()
    original_mode, original_host = settings.auth_email_mode, settings.smtp_host
    settings.auth_email_mode, settings.smtp_host = "smtp", None
    try:
        with pytest.raises(mailer.MailDeliveryError) as excinfo:
            mailer.send(
                mailer.Message(to="a@b.c", subject="s", body="b"), settings=settings
            )
        assert "SMTP_HOST" in str(excinfo.value)
    finally:
        settings.auth_email_mode, settings.smtp_host = original_mode, original_host


async def test_a_delivery_failure_surfaces_as_502_not_a_silent_success(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user told "check your email" for mail that never left is worse off
    than one told delivery failed."""
    from app.services.auth import mailer, reset_service

    creds = {
        "email": "smtp-fail@gummy.local",
        "password": "Str0ng-Passw0rd!",
        "display_name": "SMTP Fail",
    }
    signup = await api_client.post("/api/v1/auth/signup", json=creds)
    assert signup.status_code in (200, 201), signup.text

    def _boom(message: Any, *, settings: Any) -> None:
        raise mailer.MailDeliveryError("relay refused")

    monkeypatch.setattr(reset_service.mailer, "send", _boom)

    response = await api_client.post(
        "/api/v1/auth/forgot-password", json={"email": creds["email"]}
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "email_delivery_failed"
    # The provider's own words are not shown to the user.
    assert "relay refused" not in response.text


async def test_a_delivery_failure_for_an_unknown_address_still_says_nothing(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anti-enumeration must survive the error path.

    An unknown address never reaches the mailer, so it cannot 502 — which
    would otherwise make "did this address exist?" answerable by breaking SMTP.
    """
    from app.services.auth import mailer, reset_service

    def _boom(message: Any, *, settings: Any) -> None:
        raise mailer.MailDeliveryError("relay refused")

    monkeypatch.setattr(reset_service.mailer, "send", _boom)

    response = await api_client.post(
        "/api/v1/auth/forgot-password", json={"email": "no-such-user@gummy.local"}
    )

    assert response.status_code == 200
    assert response.json()["message"] == reset_service.GENERIC_RESET_RESPONSE


# ── An empty model reply must never reach the user ──────────────────────────


def test_an_empty_generation_becomes_an_honest_message() -> None:
    """Observed live: a Research turn ran its search, got five sources, called
    a tool, and then emitted zero characters. The user received an empty
    message bubble, which is indistinguishable from the app being broken."""
    from app.models.enums import PlanShape
    from app.schemas.agents import AgentResult, CostInfo
    from app.services.agents import compose

    empty = AgentResult(
        agent_key="research",
        output={"reply": "   "},
        cost=CostInfo(tokens=0, usd=0.0),
    )

    reply = compose.compose_reply(PlanShape.SINGLE, [("research", empty)])

    assert reply == compose.EMPTY_REPLY_FALLBACK
    assert reply.strip()


def test_a_real_reply_is_never_replaced_by_the_fallback() -> None:
    from app.models.enums import PlanShape
    from app.schemas.agents import AgentResult, CostInfo
    from app.services.agents import compose

    real = AgentResult(
        agent_key="research",
        output={"reply": "Here is what the sources say."},
        cost=CostInfo(tokens=0, usd=0.0),
    )

    reply = compose.compose_reply(PlanShape.SINGLE, [("research", real)])

    assert reply == "Here is what the sources say."


def test_a_run_with_no_results_at_all_still_says_something() -> None:
    from app.models.enums import PlanShape
    from app.services.agents import compose

    assert compose.compose_reply(PlanShape.SINGLE, []) == compose.EMPTY_REPLY_FALLBACK
