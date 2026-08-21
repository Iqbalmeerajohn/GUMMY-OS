"""The tool loop: registry, contracts, safety, and the cycle itself.

The loop is the point at which a language model's output starts causing effects,
so most of what is tested here is refusal rather than capability — what the model
cannot make happen, however confidently it asks.

That framing is not theoretical. The first probe of a local model with tools
attached, asked only to say hello, produced:

    calculator(expression="print('Hello')")

An implementation built on ``eval`` would have run it.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_TOOL_CALLS_PER_STEP, MAX_TOOL_ITERATIONS
from app.models.enums import MemoryCategory, PermissionTier, ToolRunStatus
from app.repositories import memory_repository as mem_repo
from app.repositories import tool_invocation_repository as audit_repo
from app.services.agents.tools import catalog, executor
from app.services.agents.tools.calculator import CalculatorError, calculate
from app.services.agents.tools.context import ToolContext
from app.services.agents.tools.executor import ToolOutcome
from app.services.agents.tools.loop import run_tool_loop
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.llm.base import ToolCall, ToolCallResponse


def spec(key: str) -> catalog.ToolSpec:
    """The catalog entry for ``key``, failing the test if it is missing."""
    found = catalog.get(key)
    assert found is not None, f"{key!r} is not in the catalog"
    return found


# ── Registry ─────────────────────────────────────────────────────────────────


def test_registry_lists_and_resolves() -> None:
    keys = {spec.key for spec in catalog.list_tools()}
    assert {"calculator", "memory_read", "file_search", "web_search"} <= keys
    assert catalog.exists("calculator")
    assert not catalog.exists("definitely_not_a_tool")
    assert catalog.get("calculator") is not None
    assert catalog.get("definitely_not_a_tool") is None


def test_resolve_drops_unknown_tools_rather_than_raising() -> None:
    """A stale manifest costs that agent one capability, not every turn."""
    resolved = catalog.resolve(["calculator", "removed_tool", "current_time"])
    assert [s.key for s in resolved] == ["calculator", "current_time"]


def test_modeled_tools_are_never_offered_to_the_model() -> None:
    """A capability that cannot run must not be advertised."""
    names = {
        f["function"]["name"]
        for f in catalog.function_schemas(
            ["calculator", "email_send", "social_publish"]
        )
    }
    assert names == {"calculator"}


def test_function_schema_hides_internals() -> None:
    """The model sees name, description, parameters — nothing else."""
    schema = spec("calculator").to_function_schema()
    assert set(schema) == {"type", "function"}
    assert set(schema["function"]) == {"name", "description", "parameters"}
    serialised = str(schema)
    assert "tier" not in serialised
    assert "timeout" not in serialised
    assert "executor" not in serialised


def test_tiers_drive_the_approval_requirement() -> None:
    assert not spec("calculator").requires_approval
    assert spec("email_send").requires_approval
    assert spec("social_publish").requires_approval
    assert spec("email_send").tier is PermissionTier.YELLOW
    assert spec("social_publish").tier is PermissionTier.RED


# ── The calculator cannot execute code ───────────────────────────────────────


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("123*456", 56088),
        ("2+3*4", 14),
        ("(10-2)/4", 2.0),
        ("2**10", 1024),
        ("-5+2", -3),
    ],
)
def test_calculator_evaluates_arithmetic(expression: str, expected: float) -> None:
    assert calculate(expression) == expected


@pytest.mark.parametrize(
    "hostile",
    [
        "print('Hello')",  # what the model actually emitted, unprompted
        "__import__('os').system('rm -rf /')",
        "open('/etc/passwd').read()",
        "eval('1+1')",
        "exec('x=1')",
        "os.getcwd()",
        "[x for x in range(10)]",
        "lambda: 1",
        "globals()",
        "().__class__.__bases__",
    ],
)
def test_calculator_refuses_every_code_execution_shape(hostile: str) -> None:
    """Rejection is at parse level, so there is no sandbox to out-think."""
    with pytest.raises(CalculatorError):
        calculate(hostile)


def test_calculator_bounds_resource_exhaustion() -> None:
    """``9**9**9`` is three characters of syntax and unbounded compute."""
    with pytest.raises(CalculatorError):
        calculate("9**9**9")


def test_calculator_reports_division_by_zero_as_a_tool_error() -> None:
    with pytest.raises(CalculatorError):
        calculate("1/0")


# ── Argument validation ──────────────────────────────────────────────────────


def test_validation_requires_declared_arguments() -> None:
    calculator_spec = spec("calculator")
    assert executor.validate_args(calculator_spec, {"expression": "1+1"}).valid
    result = executor.validate_args(calculator_spec, {})
    assert not result.valid
    assert "expression" in result.errors[0]


def test_validation_rejects_wrong_types() -> None:
    result = executor.validate_args(spec("calculator"), {"expression": 42})
    assert not result.valid


def test_validation_coerces_numeric_strings() -> None:
    """Models emit "5" for an integer far too often to fail the call over."""
    result = executor.validate_args(spec("memory_read"), {"query": "x", "limit": "5"})
    assert result.valid
    assert result.coerced["limit"] == 5


def test_validation_drops_unknown_arguments() -> None:
    """A plausible extra argument should not cost a working answer."""
    result = executor.validate_args(
        spec("calculator"), {"expression": "1+1", "hallucinated": "x"}
    )
    assert result.valid
    assert "hallucinated" not in result.coerced


# ── Redaction ────────────────────────────────────────────────────────────────


def test_secrets_are_redacted_before_audit() -> None:
    safe = executor.redact_args(
        {"query": "ok", "api_key": "sk-live-123", "password": "hunter2"}
    )
    assert safe["query"] == "ok"
    assert "sk-live-123" not in str(safe)
    assert "hunter2" not in str(safe)


def test_long_arguments_are_truncated_for_audit() -> None:
    safe = executor.redact_args({"query": "x" * 10_000})
    assert len(safe["query"]) < 10_000


# ── Executor outcomes ────────────────────────────────────────────────────────


async def test_executor_success(db_session: AsyncSession, seed_user: uuid.UUID) -> None:
    ctx = ToolContext(session=db_session, user_id=seed_user)
    result = await executor.run(spec("calculator"), ctx, {"expression": "6*7"})
    assert result.outcome is ToolOutcome.SUCCESS
    assert result.output is not None
    assert result.output["result"] == 42
    assert result.for_model()["ok"] is True


async def test_executor_converts_a_raising_tool_into_a_failure(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """A tool that raises must not take the conversation down with it."""
    ctx = ToolContext(session=db_session, user_id=seed_user)
    result = await executor.run(spec("calculator"), ctx, {"expression": "print('x')"})
    assert result.outcome is ToolOutcome.FAILED
    assert result.error
    assert result.for_model()["ok"] is False


async def test_executor_enforces_the_timeout(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    async def _hang(context: Any, args: dict) -> dict:
        await asyncio.sleep(10)
        return {}

    slow = catalog.ToolSpec(
        key="slow",
        tier=PermissionTier.GREEN,
        description="hangs",
        executor=_hang,
        timeout_seconds=0.05,
    )
    ctx = ToolContext(session=db_session, user_id=seed_user)
    result = await executor.run(slow, ctx, {})
    assert result.outcome is ToolOutcome.TIMEOUT


async def test_executor_reports_a_modeled_tool_as_unavailable(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    ctx = ToolContext(session=db_session, user_id=seed_user)
    result = await executor.run(spec("email_send"), ctx, {})
    assert result.outcome is ToolOutcome.UNAVAILABLE


# ── The loop ─────────────────────────────────────────────────────────────────


class _ScriptedLLM:
    """A model that returns a scripted sequence of turns."""

    name = "scripted"

    def __init__(self, turns: list[ToolCallResponse]) -> None:
        self._turns = turns
        self.calls = 0
        self.systems: list[str] = []

    async def generate_with_tools(
        self, *, system: str, messages: list[dict], tools: list[dict], **kw: Any
    ) -> ToolCallResponse:
        self.systems.append(system)
        turn = self._turns[min(self.calls, len(self._turns) - 1)]
        self.calls += 1
        return turn


def _answer(text: str) -> ToolCallResponse:
    return ToolCallResponse(
        text=text,
        tool_calls=[],
        model="scripted",
        input_tokens=1,
        output_tokens=1,
        stop_reason="stop",
    )


def _wants(name: str, args: dict) -> ToolCallResponse:
    return ToolCallResponse(
        text="",
        tool_calls=[ToolCall(id=f"c{name}", name=name, arguments=args)],
        model="scripted",
        input_tokens=1,
        output_tokens=1,
        stop_reason="tool_calls",
    )


async def _drive(  # type: ignore[no-untyped-def]
    session, llm, user_id, *, tool_keys=("calculator",), run_id=None, **kw
):
    events: list[dict] = []
    result = None
    async for event in run_tool_loop(
        session,
        system="sys",
        messages=[{"role": "user", "content": "q"}],
        tool_keys=tool_keys,
        llm=llm,
        agent_key="general",
        run_id=run_id or uuid.uuid4(),
        user_id=user_id,
        context=ToolContext(session=session, user_id=user_id),
        **kw,
    ):
        if event["type"] == "result":
            result = event["result"]
        else:
            events.append(event)
    return events, result


async def test_loop_returns_a_final_answer_without_calling_tools(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    llm = _ScriptedLLM([_answer("42 is the answer.")])
    events, result = await _drive(db_session, llm, seed_user)

    assert result.text == "42 is the answer."
    assert result.executions == []
    assert llm.calls == 1
    assert not any(e["type"] == "tool_status" for e in events)


async def test_loop_executes_one_tool_then_answers(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    llm = _ScriptedLLM(
        [_wants("calculator", {"expression": "123*456"}), _answer("It is 56088.")]
    )
    events, result = await _drive(db_session, llm, seed_user)

    assert result.text == "It is 56088."
    assert len(result.executions) == 1
    assert result.executions[0].outcome is ToolOutcome.SUCCESS
    assert result.executions[0].output["result"] == 56088
    stages = [e["stage"] for e in events]
    assert stages == ["tool_requested", "tool_running", "tool_completed"]


async def test_loop_handles_multiple_sequential_tool_calls(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    llm = _ScriptedLLM(
        [
            _wants("calculator", {"expression": "2*3"}),
            _wants("current_time", {}),
            _answer("Done."),
        ]
    )
    _events, result = await _drive(
        db_session, llm, seed_user, tool_keys=("calculator", "current_time")
    )

    assert result.text == "Done."
    assert [e.tool_key for e in result.executions] == ["calculator", "current_time"]
    assert result.iterations == 3


async def test_loop_feeds_a_tool_failure_back_instead_of_crashing(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """The model is told the tool failed, and gets to respond to that."""
    llm = _ScriptedLLM(
        [
            _wants("calculator", {"expression": "print('hi')"}),
            _answer("That expression isn't arithmetic."),
        ]
    )
    events, result = await _drive(db_session, llm, seed_user)

    assert result.text == "That expression isn't arithmetic."
    assert result.executions[0].outcome is ToolOutcome.FAILED
    assert any(e["stage"] == "tool_failed" for e in events)


async def test_loop_reports_an_unknown_tool_as_denied(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """A hallucinated tool name is refused, not executed."""
    llm = _ScriptedLLM([_wants("delete_everything", {}), _answer("I can't do that.")])
    _events, result = await _drive(db_session, llm, seed_user)

    assert result.executions[0].outcome is ToolOutcome.DENIED


async def test_loop_denies_a_tool_the_agent_does_not_declare(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """The manifest is the authority, not the model's request.

    ``web_search`` exists and is executable, but the general agent does not
    declare it, so the policy engine blocks the call.
    """
    llm = _ScriptedLLM([_wants("web_search", {"query": "x"}), _answer("no")])
    _events, result = await _drive(
        db_session, llm, seed_user, tool_keys=("web_search",)
    )

    assert result.executions[0].outcome is ToolOutcome.DENIED


async def test_loop_stops_at_the_iteration_cap(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """A model that never stops calling tools is stopped for it."""
    llm = _ScriptedLLM([_wants("calculator", {"expression": "1+1"})])
    _events, result = await _drive(db_session, llm, seed_user)

    assert result.hit_iteration_cap
    assert result.iterations == MAX_TOOL_ITERATIONS
    assert llm.calls == MAX_TOOL_ITERATIONS
    assert result.text, "the cap must still produce something to say"


async def test_loop_warns_the_model_on_its_final_iteration(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """So the cap yields a real answer instead of a truncated thought."""
    llm = _ScriptedLLM([_wants("calculator", {"expression": "1+1"})])
    await _drive(db_session, llm, seed_user)

    assert "no further tool calls" in llm.systems[-1].lower()
    assert "no further tool calls" not in llm.systems[0].lower()


async def test_loop_caps_a_fan_out_of_calls_in_one_step(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    burst = ToolCallResponse(
        text="",
        tool_calls=[
            ToolCall(id=f"c{i}", name="calculator", arguments={"expression": f"{i}+1"})
            for i in range(10)
        ],
        model="scripted",
        input_tokens=1,
        output_tokens=1,
        stop_reason="tool_calls",
    )
    llm = _ScriptedLLM([burst, _answer("done")])
    _events, result = await _drive(db_session, llm, seed_user)

    assert len(result.executions) == MAX_TOOL_CALLS_PER_STEP


async def test_loop_is_skipped_when_the_provider_cannot_call_tools(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Selecting a non-tool model is a limitation, not an outage."""

    class _Plain:
        name = "plain"

    _events, result = await _drive(db_session, _Plain(), seed_user)
    assert result is None


async def test_loop_is_skipped_when_the_agent_declares_no_tools(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    llm = _ScriptedLLM([_answer("hi")])
    _events, result = await _drive(db_session, llm, seed_user, tool_keys=())
    assert result is None
    assert llm.calls == 0


# ── Audit ────────────────────────────────────────────────────────────────────


async def test_every_invocation_writes_an_audit_row(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    run_id = uuid.uuid4()
    llm = _ScriptedLLM([_wants("calculator", {"expression": "2+2"}), _answer("4")])
    await _drive(db_session, llm, seed_user, run_id=run_id)
    await db_session.commit()

    rows = await audit_repo.list_for_run(db_session, run_id=run_id, user_id=seed_user)
    assert len(rows) == 1
    assert rows[0].tool_key == "calculator"
    assert rows[0].status is ToolRunStatus.SUCCEEDED
    assert rows[0].agent_key == "general"


async def test_a_refused_call_is_audited_too(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """A blocked call is evidence and must leave a trace."""
    run_id = uuid.uuid4()
    llm = _ScriptedLLM([_wants("nope", {}), _answer("can't")])
    await _drive(db_session, llm, seed_user, run_id=run_id)
    await db_session.commit()

    rows = await audit_repo.list_for_run(db_session, run_id=run_id, user_id=seed_user)
    assert len(rows) == 1
    assert rows[0].status is ToolRunStatus.NOT_EXECUTED


async def test_audit_row_never_stores_a_secret(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    run_id = uuid.uuid4()
    llm = _ScriptedLLM(
        [
            _wants("calculator", {"expression": "1+1", "api_key": "sk-live-SECRET"}),
            _answer("2"),
        ]
    )
    await _drive(db_session, llm, seed_user, run_id=run_id)
    await db_session.commit()

    rows = await audit_repo.list_for_run(db_session, run_id=run_id, user_id=seed_user)
    assert "sk-live-SECRET" not in str(rows[0].args)


# ── Tenant isolation ─────────────────────────────────────────────────────────


async def test_memory_tool_is_scoped_to_the_calling_user(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The user id comes from the context, never from tool arguments.

    A model that asks for someone else's memories searches its own.
    """
    other_user = uuid.uuid4()

    async def _fake_search(session, *, user_id, **kw):  # type: ignore[no-untyped-def]
        items, _ = await mem_repo.list_memories(
            session, user_id=user_id, limit=10, offset=0
        )
        return [(m, 0.1) for m in items]

    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await mem_repo.create_memory(
        db_session,
        user_id=seed_user,
        category=MemoryCategory.PROFILE,
        content="Belongs to the seeded user",
        importance_score=0.5,
        confidence_score=0.5,
    )
    await db_session.commit()

    ctx = ToolContext(
        session=db_session,
        user_id=seed_user,
        embedding_service=EmbeddingService(FakeEmbeddingProvider()),
    )
    # The arguments try to widen the scope; the context wins.
    result = await executor.run(
        spec("memory_read"),
        ctx,
        {"query": "anything", "user_id": str(other_user)},
    )

    assert result.outcome is ToolOutcome.SUCCESS
    assert result.output is not None
    contents = [m["content"] for m in result.output["memories"]]
    assert contents == ["Belongs to the seeded user"]


# ── Web search refuses rather than fabricating ───────────────────────────────


async def test_web_search_is_unavailable_without_a_live_provider(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Verified live before it was fixed: with the offline placeholder
    installed, the tool reported SUCCESS with mock rows and the model relayed
    them to the user as "results from a search". A tool that cannot do its job
    must say so."""
    from app.services.search import provider as search_provider

    assert not search_provider.is_live(), "the offline provider is the default"

    ctx = ToolContext(session=db_session, user_id=seed_user)
    result = await executor.run(spec("web_search"), ctx, {"query": "anything"})

    assert result.outcome is ToolOutcome.FAILED
    assert "not configured" in (result.error or "")
    assert result.output is None


async def test_web_search_runs_when_a_provider_is_configured(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    from app.services.search import provider as search_provider
    from app.services.search.provider import SearchResult

    class _Stub:
        async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
            return [
                SearchResult(title="T", url="https://e.com", snippet="s", source="stub")
            ]

    original = search_provider.get_provider()
    search_provider.set_provider(_Stub())
    try:
        ctx = ToolContext(session=db_session, user_id=seed_user)
        result = await executor.run(spec("web_search"), ctx, {"query": "x"})
    finally:
        search_provider.set_provider(original)

    assert result.outcome is ToolOutcome.SUCCESS
    assert result.output is not None
    assert result.output["results"][0]["url"] == "https://e.com"
    # Search results are data the model may cite, never instructions.
    assert "untrusted" not in result.output
