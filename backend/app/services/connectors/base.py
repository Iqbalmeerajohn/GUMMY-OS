"""Connectors — turning the user's own data elsewhere into GUMMY's memory.

A connector's job is narrow: read something the user already has (a calendar, a
mailbox, a location history export) and emit :class:`Signal` objects. Everything
after that — deduplication, scoring, versioning, embedding — is the existing
Memory Engine, reached through ``memory_service.create_memory``. That is what
keeps a connector small enough to be worth having: importing the same calendar
twice reinforces the facts instead of duplicating them, for free, because
consolidation already runs on the write path.

Two rules hold for every connector, present and future:

* **Local and explicit.** Data is pulled only when the user asks for it, over a
  credential they supplied, and lands in the same local Postgres as everything
  else. Nothing is sent anywhere.
* **Episodic by default.** Imported items are things that *happened*, so they
  carry ``occurred_at`` — which is what makes "what did I do last week" answer
  from real events rather than from what was typed in chat.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory
from app.models.memory import Memory
from app.schemas.memory import MemoryCreate
from app.services.memory import memory_service, user_profile_service

logger = logging.getLogger(__name__)

# Per import. A connector that would write thousands of memories is not
# enriching the portrait, it is burying it — and every one of those rows would
# then compete for space in the prompt.
MAX_SIGNALS_PER_IMPORT = 200


@dataclass(frozen=True)
class Signal:
    """One durable thing a connector found, ready to become a memory."""

    content: str
    category: MemoryCategory
    # When it happened. None only for genuinely timeless facts.
    occurred_at: datetime | None = None


async def ingest(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    signals: list[Signal],
) -> list[Memory]:
    """Store connector signals as memories, reusing the whole Memory Engine.

    Best-effort per signal: one malformed item must not abandon the rest of an
    import the user is waiting on.
    """
    created: list[Memory] = []
    for signal in signals[:MAX_SIGNALS_PER_IMPORT]:
        try:
            memory = await memory_service.create_memory(
                session,
                user_id=user_id,
                payload=MemoryCreate(category=signal.category, content=signal.content),
            )
        except Exception:
            logger.exception("connector signal could not be stored; skipping")
            continue
        if signal.occurred_at is not None and memory.occurred_at is None:
            memory.occurred_at = signal.occurred_at
        created.append(memory)

    if created:
        await session.commit()
        await user_profile_service.refresh_traits(session, user_id=user_id)
        await session.commit()
    return created
