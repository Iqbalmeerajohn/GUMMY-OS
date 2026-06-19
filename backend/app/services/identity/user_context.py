"""User Context layer — authenticated profile available to every agent.

Profile (account identity: name, email, status) is deliberately separate from
Memory (learned facts, preferences, goals). This module turns the verified
``CurrentUser`` into a safe, prompt-ready identity block that the shared prompt
builder injects for *every* turn — so each agent automatically knows who the user
is without retrieving it from memory and without per-agent code.

Security: only safe profile fields are exposed. Internal identifiers (user id),
tokens, and secrets are never rendered into the prompt.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class UserContext:
    """Safe, agent-facing snapshot of the authenticated account."""

    user_id: uuid.UUID
    name: str | None
    email: str | None

    @property
    def profile_completed(self) -> bool:
        return bool(self.name)


def build_identity_block(context: UserContext | None) -> str | None:
    """Render the system-prompt profile block, or ``None`` when no name is known.

    Returning ``None`` (anonymous / name unset) leaves the prompt byte-identical
    to the pre-injection behavior, so memory-only grounding still applies.
    """
    if context is None or not context.name:
        return None

    lines = [f"- Name: {context.name}"]
    if context.email:
        lines.append(f"- Email: {context.email}")
    lines.append("- Account status: Active")
    profile = "\n".join(lines)

    return (
        "Authenticated user profile — the user's verified ACCOUNT data, distinct "
        "from remembered memories:\n"
        f"<user_profile>\n{profile}\n</user_profile>\n"
        "Treat this profile as known and current. Use it to answer questions "
        "about the user's identity (e.g. their name or who they are), and prefer "
        "it over <memory> for identity/account questions. Do not reveal internal "
        "identifiers (user IDs) or tokens unless the user explicitly asks."
    )
