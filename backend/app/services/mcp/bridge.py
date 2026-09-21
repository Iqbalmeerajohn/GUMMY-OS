"""Installing discovered MCP tools into the tool catalog.

One function does the interesting work: turning a ``DiscoveredTool`` into a
``ToolSpec`` whose executor dials the server. Everything else in this module
is startup plumbing.

A note on connection lifetime. Each call opens a connection, runs the tool,
and closes it, rather than holding a long-lived session per server. That is
slower — a stdio server pays process startup every time — and it is the right
default here:

* a wedged or crashed server cannot poison later calls;
* a subprocess cannot sit resident for the life of the backend holding file
  handles or memory;
* the failure mode is one slow call, not a silently dead integration.

If a server turns out to be hot enough that startup cost matters, pooling
belongs here, behind the same interface, and should be added with a timeout
and a health check rather than by keeping the first connection forever.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from app.core.config import get_settings
from app.services.agents.tools.catalog import (
    CatalogSealedError,
    ToolSpec,
    install_external_tools,
)
from app.services.mcp.client import MCPClient, MCPError
from app.services.mcp.registry import (
    DiscoveredTool,
    MCPConfigError,
    discover_all,
    parse_config,
)

logger = logging.getLogger(__name__)

# Generous: a stdio server may have to install itself on first use, and the
# executor's own timeout is what actually bounds a turn.
EXTERNAL_TOOL_TIMEOUT_SECONDS = 60.0


def _make_executor(
    tool: DiscoveredTool,
) -> Callable[[object, dict], Awaitable[dict]]:
    """Build the executor closure for one discovered tool."""

    async def execute(context: object, args: dict) -> dict:
        async with MCPClient(tool.server.transport, name=tool.server.name) as client:
            result = await client.call_tool(tool.definition.name, args)
        if result.get("is_error"):
            # The server reported a tool-level failure in-band. Raise so the
            # executor records it as FAILED rather than a successful result
            # whose content happens to be an error message.
            raise MCPError(
                f"{tool.definition.name} failed: {result.get('content', '')[:300]}"
            )
        return {
            "server": tool.server.name,
            "tool": tool.definition.name,
            "content": result.get("content", ""),
            "truncated": result.get("truncated", False),
        }

    return execute


def to_spec(tool: DiscoveredTool) -> ToolSpec:
    """The catalog entry for one discovered tool."""
    return ToolSpec(
        key=tool.key,
        tier=tool.tier,
        description=tool.description,
        executor=_make_executor(tool),
        display_name=f"{tool.definition.name} ({tool.server.name})",
        category="external",
        parameters=tool.parameters,
        timeout_seconds=EXTERNAL_TOOL_TIMEOUT_SECONDS,
    )


async def install_configured_servers() -> list[str]:
    """Discover every configured MCP server and install its tools.

    Called once from the application lifespan. Never raises: a misconfigured
    or unreachable MCP server must not stop the backend from starting.
    """
    settings = get_settings()
    if not settings.gummy_mcp_enabled:
        return []

    try:
        servers = parse_config(settings.gummy_mcp_servers)
    except MCPConfigError as exc:
        logger.warning("MCP disabled: %s", exc)
        return []
    if not servers:
        return []

    discovered = await discover_all(servers)
    if not discovered:
        return []

    try:
        return install_external_tools([to_spec(tool) for tool in discovered])
    except CatalogSealedError:
        # Only reachable if startup ran twice in one process (some test
        # harnesses do this). Harmless, and worth saying out loud.
        logger.warning("external tools already installed; skipping")
        return []
