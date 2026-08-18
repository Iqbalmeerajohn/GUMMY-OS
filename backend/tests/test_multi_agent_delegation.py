"""Multi-agent delegation: compound detection, hand-off, and what must NOT fan out.

The hard part of compound routing is not detecting two capabilities — it is
refusing to detect two when there is only one. "Find AI/ML fresher jobs and
internships" fires four career keywords and is a single task; "find jobs and
then build a learning plan" fires career and learning and is two. Counting
keywords cannot tell those apart, so detection is grammatical: a request only
fans out when a connective separates clauses that resolve to *different*
specialists.

Roughly half the tests here assert that a request stays single-agent.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory, PlanShape
from app.repositories import agent_message_repository as a2a_repo
from app.repositories import agent_run_repository as run_repo
from app.repositories import memory_repository as mem_repo
from app.schemas.agents import AgentHandoff, AgentResult, ContextPack, RoutingDecision
from app.schemas.conversation import ConversationCreate
from app.services.agents import orchestrator_service, router
from app.services.agents.handlers import grounding
from app.services.agents.orchestrator_service import (
    _build_handoff,
    _extract_findings,
)
from app.services.agents.registry import get_registry
from app.services.agents.router import plan_compound, split_clauses
from app.services.conversation import conversation_service
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.llm.fake_provider import FakeLLMProvider


def _registry() -> Any:
    return get_registry()


async def _route(intent: str) -> RoutingDecision:
    return await router.route(intent=intent, registry=_registry())


def _chain(decision: RoutingDecision) -> list[str]:
    return [s.agent_key for s in decision.steps]


# ── Clause splitting ─────────────────────────────────────────────────────────


def test_a_request_without_a_connective_is_one_clause() -> None:
    assert len(split_clauses("Find AI/ML fresher opportunities for me")) == 1


def test_connectives_split_a_request() -> None:
    clauses = split_clauses("Find AI jobs and then create a learning plan")
    assert len(clauses) == 2
    assert "Find AI jobs" in clauses[0]


def test_fragments_are_discarded() -> None:
    """ "and ok" is punctuation noise, not a task worth an agent."""
    assert split_clauses("Teach me Python and ok") == ["Teach me Python"]


# ── Compound detection: the fan-out cases ────────────────────────────────────


async def test_career_then_learning() -> None:
    decision = await _route(
        "Find AI/ML fresher jobs suitable for me and create a learning plan "
        "for the biggest skill gap."
    )
    assert decision.plan_shape is PlanShape.PIPELINE
    assert _chain(decision) == ["career", "learning"]


async def test_research_then_learning() -> None:
    decision = await _route(
        "Research LangGraph and then teach me the most important concepts."
    )
    assert decision.plan_shape is PlanShape.PIPELINE
    assert _chain(decision) == ["research", "learning"]


async def test_three_clause_request_chains_two_specialists() -> None:
    """The third clause has no specialist, so it folds into the previous step
    rather than being dropped — its wording still reaches an agent."""
    decision = await _route(
        "Find suitable AI jobs, research the companies, and tell me how I "
        "should prepare."
    )
    assert decision.plan_shape is PlanShape.PIPELINE
    assert _chain(decision) == ["career", "research"]
    assert "prepare" in (decision.steps[-1].intent or "")


async def test_clause_order_is_execution_order() -> None:
    """ "Research X then teach me" runs Research first — the order stated."""
    decision = await _route("Research LangGraph and then teach me about it")
    assert _chain(decision)[0] == "research"


async def test_each_step_carries_only_its_own_clause() -> None:
    decision = await _route(
        "Find AI jobs for me and then build a learning plan for the gap"
    )
    first, second = decision.steps
    assert "job" in (first.intent or "").lower()
    assert "learning plan" in (second.intent or "").lower()


# ── What must NOT fan out ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        ("Find AI/ML fresher opportunities suitable for me.", "career"),
        ("Teach me Python", "learning"),
        ("Research the AI agent market", "research"),
        ("Remind me tomorrow at 9 AM to review my goals", "automation"),
    ],
)
async def test_single_capability_requests_stay_single(
    intent: str, expected: str
) -> None:
    """The regression guard: existing single-agent behaviour is unchanged."""
    decision = await _route(intent)
    assert decision.plan_shape is PlanShape.SINGLE
    assert _chain(decision) == [expected]


async def test_two_clauses_wanting_the_same_agent_collapse() -> None:
    """ "jobs and internships" is one task phrased with a connective."""
    decision = await _route("Find AI/ML fresher jobs and internships")
    assert decision.plan_shape is PlanShape.SINGLE
    assert _chain(decision) == ["career"]


async def test_a_noun_list_does_not_fan_out() -> None:
    """Commas split, but the two-distinct-specialists guard collapses it back.

    This is why a bare comma is safe as a separator.
    """
    decision = await _route("Find me AI jobs in Bangalore, Chennai, or Pune")
    assert decision.plan_shape is PlanShape.SINGLE
    assert _chain(decision) == ["career"]


async def test_automation_owns_a_scheduled_learning_request() -> None:
    """ "Remind me tomorrow to study X" is scheduling, not teaching."""
    decision = await _route("Remind me tomorrow to study LangGraph")
    assert decision.plan_shape is PlanShape.SINGLE
    assert _chain(decision) == ["automation"]


async def test_an_unrecognised_request_falls_back_to_general() -> None:
    decision = await _route("what is the capital of France")
    assert decision.plan_shape is PlanShape.SINGLE
    assert _chain(decision) == ["general"]


async def test_a_connective_with_no_specialists_stays_general() -> None:
    decision = await _route("tell me a joke and make it funny")
    assert _chain(decision) == ["general"]


async def test_manual_override_beats_compound_detection() -> None:
    """A pinned agent is the user's explicit instruction."""
    decision = await router.route(
        intent="Find AI jobs and then create a learning plan",
        registry=_registry(),
        forced_agent_key="research",
    )
    assert decision.plan_shape is PlanShape.SINGLE
    assert _chain(decision) == ["research"]


async def test_an_unknown_override_degrades_to_general() -> None:
    decision = await router.route(
        intent="Find AI jobs and then create a learning plan",
        registry=_registry(),
        forced_agent_key="does_not_exist",
    )
    assert _chain(decision) == ["general"]


def test_compound_is_capped() -> None:
    """A runaway list of clauses cannot spawn unbounded agents."""
    from app.core.constants import COMPOUND_MAX_STEPS

    intent = (
        "find jobs, and research companies, and teach me python, "
        "and remind me tomorrow, and research more things"
    )
    decision = plan_compound(intent, _registry())
    assert decision is not None
    assert len(decision.steps) <= COMPOUND_MAX_STEPS


# ── Routing metadata stays safe ──────────────────────────────────────────────


async def test_compound_exposes_safe_routing_metadata() -> None:
    decision = await _route("Find AI jobs and then create a learning plan")

    assert decision.rationale.startswith("compound request:")
    assert "career" in decision.rationale and "learning" in decision.rationale
    assert decision.matched_keywords
    assert 0.0 < decision.confidence <= 1.0


# ── Structured hand-off ──────────────────────────────────────────────────────


def test_findings_are_extracted_from_bullets() -> None:
    """Agents already answer in bullets, so the bullets ARE the findings —
    no extra model call to summarise text the agent just wrote."""
    reply = "Skill Gaps\n- Missing skill: LangGraph\n- Target role: AI Engineer\n"
    assert _extract_findings(reply) == [
        "Missing skill: LangGraph",
        "Target role: AI Engineer",
    ]


def test_findings_fall_back_to_sentences_for_prose() -> None:
    reply = (
        "You are a strong fit for AI engineering roles. "
        "The clearest gap is orchestration frameworks like LangGraph."
    )
    findings = _extract_findings(reply)
    assert findings
    assert "AI engineering" in findings[0]


def test_handoff_carries_findings_not_the_whole_reply() -> None:
    result = AgentResult(
        output={"reply": "Gaps\n- Missing: LangGraph\n- Role: AI Engineer"}
    )
    handoff = _build_handoff(
        source_agent="career", target_agent="learning", result=result
    )

    assert handoff.source_agent == "career"
    assert handoff.target_agent == "learning"
    assert "Missing: LangGraph" in handoff.relevant_findings
    assert handoff.recommended_next_action


def test_handoff_renders_as_a_prompt_block() -> None:
    rendered = AgentHandoff(
        source_agent="career",
        target_agent="learning",
        relevant_findings=["Missing skill: LangGraph"],
        recommended_next_action="Build a plan.",
    ).render()

    assert "career agent" in rendered
    assert "Missing skill: LangGraph" in rendered
    assert "Build a plan." in rendered


async def test_the_receiving_agent_actually_sees_the_handoff() -> None:
    """The gap this milestone closed.

    Grounding previously read only a ``digest`` key, which specialists never
    produce — so a career→learning pipeline handed the learning agent nothing
    and it answered as though the first step had never run.
    """
    from app.schemas.agents import AgentTask

    task = AgentTask(
        run_id=uuid.uuid4(),
        agent_key="learning",
        intent="create a learning plan",
        context_pack=ContextPack(
            scratch=[
                {
                    "agent_key": "career",
                    "output": {"reply": "irrelevant"},
                    "handoff": AgentHandoff(
                        source_agent="career",
                        target_agent="learning",
                        relevant_findings=["Missing skill: LangGraph"],
                        recommended_next_action="Build a plan.",
                    ).model_dump(),
                }
            ]
        ),
    )

    prepared = await grounding.prepare(task)

    assert "Missing skill: LangGraph" in prepared.system
    assert "career agent" in prepared.system


async def test_a_single_agent_prompt_has_no_handoff_block() -> None:
    """Empty scratch must leave the single-agent prompt unchanged."""
    from app.schemas.agents import AgentTask

    task = AgentTask(run_id=uuid.uuid4(), agent_key="career", intent="find jobs")
    prepared = await grounding.prepare(task)

    assert "handed over by" not in prepared.system


async def test_the_recall_digest_handoff_still_works() -> None:
    """The pre-existing shape must keep flowing after the new one was added."""
    from app.schemas.agents import AgentTask

    task = AgentTask(
        run_id=uuid.uuid4(),
        agent_key="general",
        intent="what do you know",
        context_pack=ContextPack(
            scratch=[{"agent_key": "recall", "output": {"digest": "Lives in Vizag"}}]
        ),
    )
    prepared = await grounding.prepare(task)

    assert "Lives in Vizag" in prepared.system


# ── Execution + A2A persistence ──────────────────────────────────────────────


async def _fake_search(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query_vector: list[float],
    embedding_model: str,
    limit: int,
    include_archived: bool = False,
    category: MemoryCategory | None = None,
) -> list[tuple[Any, float]]:
    items, _ = await mem_repo.list_memories(
        session, user_id=user_id, limit=limit, offset=0
    )
    return [(m, 0.2) for m in items]


async def _new_conv(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    conv = await conversation_service.create_conversation(
        session, user_id=user_id, payload=ConversationCreate()
    )
    return conv.id


async def test_a_compound_turn_executes_both_agents_and_traces_them(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: two steps run, both are recorded, and the A2A hops persist."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    conversation_id = await _new_conv(db_session, seed_user)

    result = await orchestrator_service.orchestrate(
        db_session,
        user_id=seed_user,
        conversation_id=conversation_id,
        message=("Find AI jobs for me and then create a learning plan for the gap"),
        embedding_service=EmbeddingService(FakeEmbeddingProvider()),
        llm=FakeLLMProvider(reply="- Missing skill: LangGraph"),
    )
    await db_session.commit()

    assert result.message_metadata is not None
    assert result.message_metadata["route_shape"] == PlanShape.PIPELINE.value

    runs = await run_repo.list_for_conversation(
        db_session, conversation_id=conversation_id, user_id=seed_user, limit=5
    )
    assert len(runs) == 1
    assert runs[0].route_plan["steps"] == ["career", "learning"]

    hops = await a2a_repo.list_for_run(db_session, run_id=runs[0].id, user_id=seed_user)
    agents_seen = {h.to_agent for h in hops if h.to_agent} | {
        h.from_agent for h in hops
    }
    assert "career" in agents_seen
    assert "learning" in agents_seen


async def test_a_hop_payload_never_carries_reasoning(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Traces are evidence, not transcripts: previews only."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    conversation_id = await _new_conv(db_session, seed_user)

    await orchestrator_service.orchestrate(
        db_session,
        user_id=seed_user,
        conversation_id=conversation_id,
        message="Find AI jobs and then create a learning plan",
        embedding_service=EmbeddingService(FakeEmbeddingProvider()),
        llm=FakeLLMProvider(reply="- Missing: LangGraph"),
    )
    await db_session.commit()

    runs = await run_repo.list_for_conversation(
        db_session, conversation_id=conversation_id, user_id=seed_user, limit=1
    )
    hops = await a2a_repo.list_for_run(db_session, run_id=runs[0].id, user_id=seed_user)
    for hop in hops:
        keys = set(hop.payload or {})
        assert not keys & {"system", "prompt", "reasoning", "messages"}


async def test_a_compound_turn_still_produces_one_reply(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The terminal agent IS the synthesiser — its answer already incorporates
    the upstream findings, so the user gets one reply, not two concatenated."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    conversation_id = await _new_conv(db_session, seed_user)

    result = await orchestrator_service.orchestrate(
        db_session,
        user_id=seed_user,
        conversation_id=conversation_id,
        message="Find AI jobs and then create a learning plan",
        embedding_service=EmbeddingService(FakeEmbeddingProvider()),
        llm=FakeLLMProvider(reply="Here is the plan."),
    )

    assert result.reply == "Here is the plan."
    assert result.message_metadata is not None
    assert result.message_metadata["agent_key"] == "learning"


async def test_a_failing_first_step_does_not_crash_the_turn(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pipeline failure raises so ``run_turn``'s fallback can answer — the
    user never loses a reply to an orchestration fault."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )

    async def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("career exploded")

    monkeypatch.setattr("app.services.agents.handlers.dispatch", _boom)
    conversation_id = await _new_conv(db_session, seed_user)

    with pytest.raises(RuntimeError):
        await orchestrator_service.orchestrate(
            db_session,
            user_id=seed_user,
            conversation_id=conversation_id,
            message="Find AI jobs and then create a learning plan",
            embedding_service=EmbeddingService(FakeEmbeddingProvider()),
            llm=FakeLLMProvider(reply="x"),
        )
    await db_session.rollback()


# ── Tool ceilings still hold across a pipeline ──────────────────────────────


def test_each_agent_in_a_pipeline_keeps_its_own_tool_ceiling() -> None:
    """Delegation must not widen capability: Automation has no web access
    however it is reached."""
    from app.services.agents.orchestrator_service import _agent_tool_keys

    assert "web_search" in _agent_tool_keys("research")
    assert "web_search" not in _agent_tool_keys("automation")
    assert "automation_create" not in _agent_tool_keys("career")


# ── The trace endpoint ───────────────────────────────────────────────────────


async def test_the_run_trace_endpoint_returns_the_pipeline(
    api_client: Any, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Found live: the endpoint 500'd because it read step fields that do not
    exist on the model. A response model is not a schema check — only calling
    the endpoint proves the attribute names are real."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    params = {"user_id": str(seed_user)}
    created = await api_client.post("/api/v1/conversations", params=params, json={})
    conversation_id = created.json()["id"]

    await api_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        params=params,
        json={"message": "Find AI jobs and then create a learning plan"},
    )

    listed = await api_client.get(
        "/api/v1/runs", params={**params, "conversation_id": conversation_id}
    )
    assert listed.status_code == 200
    runs = listed.json()
    assert runs and runs[0]["route_plan"]["steps"] == ["career", "learning"]

    detail = await api_client.get(f"/api/v1/runs/{runs[0]['id']}", params=params)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert [s["agent_key"] for s in body["steps"]] == ["career", "learning"]
    assert body["hops"], "A2A hops must be retrievable"


async def test_another_tenants_run_is_not_readable(
    api_client: Any, seed_user: uuid.UUID
) -> None:
    """404 rather than 403: the existence of a run id is itself information."""
    response = await api_client.get(
        f"/api/v1/runs/{uuid.uuid4()}", params={"user_id": str(seed_user)}
    )
    assert response.status_code == 404
