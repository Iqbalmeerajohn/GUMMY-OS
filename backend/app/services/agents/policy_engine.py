"""Policy Engine — the Green/Yellow/Red gate (Phase 3, M6).

Central, never per-agent (PHASE3_PLAN.md §2.5/§10). Evaluation inputs are
exclusively trusted state: the agent's manifest (code-defined), the tool's
catalog tier (code-defined), and the user's standing allowances (settings).
**Nothing an agent or external tool produces can influence a verdict** —
that is the prompt-injection invariant: untrusted content cannot escalate a
tier or self-approve an action.

Rules:
- tool not in the agent's manifest → BLOCK
- tool tier above the agent's ceiling → BLOCK
- Green → ALLOW
- Yellow → ALLOW with a standing allowance, otherwise PROMPT
- Red → always PROMPT (**no always-allow for Red**; allowances are ignored)
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from app.models.enums import PermissionTier
from app.schemas.agents import AgentManifest

_TIER_ORDER: dict[PermissionTier, int] = {
    PermissionTier.GREEN: 0,
    PermissionTier.YELLOW: 1,
    PermissionTier.RED: 2,
}


class PolicyDecision(StrEnum):
    """What the gate says about one proposed tool call/action."""

    ALLOW = "allow"
    PROMPT = "prompt"
    BLOCK = "block"


@dataclass(frozen=True)
class PolicyVerdict:
    """A gate decision plus the auditable reason."""

    decision: PolicyDecision
    reason: str


def evaluate(
    *,
    manifest: AgentManifest,
    tool_key: str,
    tool_tier: PermissionTier,
    standing_allowances: Collection[str] = (),
) -> PolicyVerdict:
    """Gate one proposed tool call. Pure function of trusted state only."""
    if tool_key not in manifest.tools:
        return PolicyVerdict(
            PolicyDecision.BLOCK,
            f"tool {tool_key!r} is not in agent {manifest.key!r}'s manifest",
        )
    if _TIER_ORDER[tool_tier] > _TIER_ORDER[manifest.ceiling]:
        return PolicyVerdict(
            PolicyDecision.BLOCK,
            f"tool tier {tool_tier.value!r} exceeds agent "
            f"{manifest.key!r}'s ceiling {manifest.ceiling.value!r}",
        )
    if tool_tier == PermissionTier.GREEN:
        return PolicyVerdict(PolicyDecision.ALLOW, "green: read-only")
    if tool_tier == PermissionTier.YELLOW:
        if tool_key in standing_allowances:
            return PolicyVerdict(PolicyDecision.ALLOW, "yellow: standing allowance")
        return PolicyVerdict(PolicyDecision.PROMPT, "yellow: requires confirmation")
    # Red: per-action human approval, always. Standing allowances ignored.
    return PolicyVerdict(
        PolicyDecision.PROMPT, "red: per-action approval required, always"
    )
