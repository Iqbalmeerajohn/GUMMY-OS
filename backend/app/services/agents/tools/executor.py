"""The tool executor — the one place a tool actually runs.

``interface.invoke`` already owns the gate (manifest check, policy verdict, audit
row). This module owns the *execution* half that sat inside it: argument
validation against the declared schema, the timeout, and turning every possible
ending — success, failure, timeout, denial, approval, unavailability — into one
structured value instead of an exception.

That matters because the caller is a conversation. A tool that raises must not
take the turn down with it: a model that asked for something impossible should
be told so and allowed to continue, exactly as a person would be. So the only
thing that escapes this module is a programming error in the framework itself.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.services.agents.tools.catalog import ToolSpec

logger = logging.getLogger(__name__)

# Argument values are echoed into the audit row, so they are bounded. A model
# can emit an arbitrarily long string, and an audit table is not a log sink.
_MAX_ARG_CHARS = 2000

# Argument names that must never reach an audit row in the clear, whatever a
# tool chooses to accept. Redaction is by key, applied before persistence.
_REDACTED_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "authorization",
        "credential",
        "credentials",
        "private_key",
        "session",
        "cookie",
    }
)
_REDACTED = "[REDACTED]"


class ToolOutcome(StrEnum):
    """How a tool invocation ended, from the agent's point of view."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    DENIED = "denied"
    APPROVAL_REQUIRED = "approval_required"
    UNAVAILABLE = "unavailable"


# Outcomes the loop should report but not retry: the request itself was refused
# or is impossible, so repeating it changes nothing.
TERMINAL_OUTCOMES = frozenset(
    {ToolOutcome.DENIED, ToolOutcome.APPROVAL_REQUIRED, ToolOutcome.UNAVAILABLE}
)


@dataclass(frozen=True)
class ToolExecution:
    """The structured result of running (or refusing to run) one tool."""

    tool_key: str
    outcome: ToolOutcome
    output: dict | None = None
    error: str | None = None
    duration_ms: float = 0.0
    approval_id: uuid.UUID | None = None
    invocation_id: uuid.UUID | None = None

    @property
    def ok(self) -> bool:
        return self.outcome is ToolOutcome.SUCCESS

    def for_model(self) -> dict:
        """What the agent is told, as JSON-serialisable data.

        A failure is reported as data rather than hidden, so the model can say
        "that didn't work" instead of inventing a result. Nothing internal —
        no invocation ids, no durations, no tier — is included.
        """
        if self.ok:
            return {"ok": True, "result": self.output or {}}
        return {"ok": False, "status": self.outcome.value, "error": self.error or ""}


def redact_args(args: dict) -> dict:
    """A copy of ``args`` safe to persist: secrets masked, values bounded."""
    safe: dict[str, Any] = {}
    for key, value in args.items():
        if key.lower() in _REDACTED_KEYS:
            safe[key] = _REDACTED
            continue
        if isinstance(value, str) and len(value) > _MAX_ARG_CHARS:
            safe[key] = value[:_MAX_ARG_CHARS] + "…[truncated]"
        else:
            safe[key] = value
    return safe


@dataclass
class ValidationResult:
    """Whether arguments satisfy a tool's declared schema."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    coerced: dict = field(default_factory=dict)


def validate_args(spec: ToolSpec, args: dict) -> ValidationResult:
    """Check ``args`` against the tool's JSON Schema.

    A deliberately small subset — required keys, top-level types, and dropping
    unknown keys — rather than a full JSON Schema engine. These schemas are
    code-defined and shallow, and the executable tools are all read-only, so the
    validation that earns its keep is "did the model supply the right fields, of
    roughly the right shape". Anything deeper is the tool's own job, where the
    error message can be specific.

    Unknown keys are dropped rather than rejected: models routinely add a
    plausible extra argument, and failing the call for that would trade a
    working answer for a pedantic one.
    """
    schema = spec.parameters or {}
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    errors: list[str] = []
    coerced: dict[str, Any] = {}

    for name in required:
        if name not in args or args[name] is None or args[name] == "":
            errors.append(f"missing required argument {name!r}")

    type_checks: dict[str, tuple[type, ...]] = {
        "string": (str,),
        "integer": (int,),
        "number": (int, float),
        "boolean": (bool,),
        "array": (list,),
        "object": (dict,),
    }
    for name, value in args.items():
        declared = properties.get(name)
        if declared is None:
            continue  # unknown key: dropped, not an error
        expected = type_checks.get(str(declared.get("type", "")))
        if expected and not isinstance(value, expected):
            # One coercion is worth doing: models emit "5" for an integer far
            # too often to fail the whole call over it.
            if expected == (int,) and isinstance(value, str) and value.isdigit():
                coerced[name] = int(value)
                continue
            errors.append(
                f"argument {name!r} should be {declared.get('type')}, "
                f"got {type(value).__name__}"
            )
            continue
        coerced[name] = value

    return ValidationResult(valid=not errors, errors=errors, coerced=coerced)


async def run(
    spec: ToolSpec,
    context: Any,
    args: dict,
) -> ToolExecution:
    """Validate and execute one tool, converting every ending into an outcome.

    Never raises for a tool's own failure. The timeout is enforced here rather
    than inside each executor so a tool cannot opt out of it.
    """
    if not spec.is_executable or spec.executor is None:
        return ToolExecution(
            tool_key=spec.key,
            outcome=ToolOutcome.UNAVAILABLE,
            error=f"{spec.name} is declared but not available in this build.",
        )

    validation = validate_args(spec, args)
    if not validation.valid:
        return ToolExecution(
            tool_key=spec.key,
            outcome=ToolOutcome.FAILED,
            error="; ".join(validation.errors),
        )

    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        output = await asyncio.wait_for(
            spec.executor(context, validation.coerced),
            timeout=spec.timeout_seconds,
        )
    except TimeoutError:
        elapsed = (loop.time() - started) * 1000
        logger.warning("tool %s timed out after %.0fs", spec.key, spec.timeout_seconds)
        return ToolExecution(
            tool_key=spec.key,
            outcome=ToolOutcome.TIMEOUT,
            error=f"{spec.name} took longer than {spec.timeout_seconds:.0f}s.",
            duration_ms=elapsed,
        )
    except Exception as exc:
        elapsed = (loop.time() - started) * 1000
        # Logged with a stack trace, reported to the model as one line. The
        # model gets enough to explain itself and nothing about our internals.
        logger.exception("tool %s failed", spec.key)
        return ToolExecution(
            tool_key=spec.key,
            outcome=ToolOutcome.FAILED,
            error=f"{type(exc).__name__}: {exc}"[:500],
            duration_ms=elapsed,
        )

    elapsed = (loop.time() - started) * 1000
    return ToolExecution(
        tool_key=spec.key,
        outcome=ToolOutcome.SUCCESS,
        output=output if isinstance(output, dict) else {"result": output},
        duration_ms=elapsed,
    )
