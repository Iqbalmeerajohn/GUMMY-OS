"""Green tool: the current date and time.

Trivial, and genuinely necessary: a model's weights have no clock, so anything
schedule-shaped ("what's the date?", "how long until Friday?") is otherwise
answered from the training cutoff with total confidence.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.agents.tools.context import ToolContext


async def execute(context: ToolContext, args: dict) -> dict:
    """Return the current UTC date and time."""
    now = datetime.now(UTC)
    return {
        "iso8601": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "timezone": "UTC",
    }
