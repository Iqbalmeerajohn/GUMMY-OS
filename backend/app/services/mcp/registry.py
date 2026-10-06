"""Turning configured MCP servers into catalog tools.

The tool catalog is code-defined and immutable at runtime, and that is a
deliberate security property: nothing a model says can add a capability. MCP
is dynamic by nature, so the two have to be reconciled rather than one giving
way to the other.

The reconciliation is: **servers are configuration, tools are discovered from
them once, at startup, and the result is frozen.** An operator edits a JSON
file and restarts; a running process never gains a tool. That keeps the
property that matters — the set of capabilities is fixed for the lifetime of a
process and decided by a human — while still letting third-party tools in.

Tiering is the other half. A server does not get to say how dangerous it is.
Every discovered tool is Yellow unless its fully-qualified name appears in the
operator's ``green`` allowlist, so the default for foreign code is "a human
approves each call", and making something Green is an explicit, per-tool,
local decision.

Namespacing: a tool advertised as ``read_file`` by the server configured as
``fs`` becomes ``mcp__fs__read_file``. Two servers cannot collide, and nothing
from a server can shadow a built-in.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.models.enums import PermissionTier
from app.services.mcp.client import (
    HttpServer,
    MCPClient,
    MCPError,
    MCPToolDefinition,
    StdioServer,
)

logger = logging.getLogger(__name__)

TOOL_PREFIX = "mcp__"
# Server ids appear in tool keys, which are 64-char DB columns and are shown to
# the model, so they are kept short and boring.
_SERVER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,23}$")


class MCPConfigError(ValueError):
    """The MCP server configuration is malformed."""


@dataclass(frozen=True)
class MCPServerConfig:
    """One configured server, as an operator wrote it."""

    name: str
    transport: StdioServer | HttpServer
    # Fully-qualified tool keys that may run without approval. Everything else
    # discovered from this server is Yellow.
    green: frozenset[str] = field(default_factory=frozenset)
    enabled: bool = True


def tool_key(server_name: str, tool_name: str) -> str:
    """The namespaced catalog key for a server's tool."""
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", tool_name)[:32]
    return f"{TOOL_PREFIX}{server_name}__{safe}"


def parse_config(
    raw: str | None, *, base_dir: Path | None = None
) -> list[MCPServerConfig]:
    """Parse the configured servers from inline JSON or a file path.

    A malformed entry is skipped with a warning rather than taking the whole
    configuration down: one bad server should cost its own tools.
    """
    if not raw or not raw.strip():
        return []

    text = raw.strip()
    if not text.startswith(("[", "{")):
        path = Path(text)
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise MCPConfigError(f"could not read MCP config {path}: {exc}") from exc

    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MCPConfigError(f"MCP config is not valid JSON: {exc}") from exc

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise MCPConfigError("MCP config must be a JSON array or object")

    servers: list[MCPServerConfig] = []
    seen: set[str] = set()
    for index, entry in enumerate(data):
        try:
            server = _parse_entry(entry, index)
        except MCPConfigError as exc:
            logger.warning("skipping MCP server %d: %s", index, exc)
            continue
        if server.name in seen:
            logger.warning("skipping duplicate MCP server id %r", server.name)
            continue
        seen.add(server.name)
        servers.append(server)
    return servers


def _parse_entry(entry: Any, index: int) -> MCPServerConfig:
    if not isinstance(entry, dict):
        raise MCPConfigError("entry is not an object")

    name = str(entry.get("name", "")).strip().lower()
    if not _SERVER_ID_PATTERN.match(name):
        raise MCPConfigError(
            f"name {name!r} must be 1-24 chars of [a-z0-9_-] starting alphanumeric"
        )

    url = entry.get("url")
    command = entry.get("command")
    transport: StdioServer | HttpServer
    if url:
        transport = HttpServer(url=str(url), token=entry.get("token"))
    elif command:
        args = entry.get("args", [])
        if not isinstance(args, list):
            raise MCPConfigError("args must be a list")
        transport = StdioServer(command=str(command), args=[str(a) for a in args])
    else:
        raise MCPConfigError("entry needs either 'url' or 'command'")

    raw_green = entry.get("green", [])
    if not isinstance(raw_green, list):
        raise MCPConfigError("green must be a list of tool names")
    # Accept either the bare server-side name or the namespaced key, so an
    # operator does not have to know the prefixing rule to use the allowlist.
    green = {
        g if g.startswith(TOOL_PREFIX) else tool_key(name, str(g)) for g in raw_green
    }

    return MCPServerConfig(
        name=name,
        transport=transport,
        green=frozenset(green),
        enabled=bool(entry.get("enabled", True)),
    )


@dataclass(frozen=True)
class DiscoveredTool:
    """A server tool, resolved to a local key and a locally-decided tier."""

    key: str
    server: MCPServerConfig
    definition: MCPToolDefinition
    tier: PermissionTier

    @property
    def description(self) -> str:
        """Model-facing description, marked with its origin.

        The provenance note is not decoration: it tells the model — and anyone
        reading an audit row — that this capability came from outside.
        """
        base = self.definition.description or f"{self.definition.name} (external)"
        return f"[via {self.server.name}] {base}"

    @property
    def parameters(self) -> dict:
        schema = dict(self.definition.input_schema or {})
        # The executor and native tool-calling both require an object schema;
        # a server that omits the type gets a permissive but valid one.
        if schema.get("type") != "object":
            return {"type": "object", "properties": schema.get("properties", {})}
        return schema


async def discover(server: MCPServerConfig) -> list[DiscoveredTool]:
    """Connect to one server and return its tools. Never raises."""
    if not server.enabled:
        return []
    try:
        async with MCPClient(server.transport, name=server.name) as client:
            definitions = await client.list_tools()
    except (MCPError, OSError) as exc:
        logger.warning("MCP server %r unavailable: %s", server.name, exc)
        return []
    except Exception:  # noqa: BLE001 - a third-party server must not crash boot
        logger.exception("MCP server %r failed during discovery", server.name)
        return []

    tools: list[DiscoveredTool] = []
    for definition in definitions:
        key = tool_key(server.name, definition.name)
        tier = PermissionTier.GREEN if key in server.green else PermissionTier.YELLOW
        tools.append(
            DiscoveredTool(key=key, server=server, definition=definition, tier=tier)
        )
    logger.info("discovered %d tool(s) from MCP server %r", len(tools), server.name)
    return tools


async def discover_all(servers: list[MCPServerConfig]) -> list[DiscoveredTool]:
    """Discover across every configured server, skipping the broken ones."""
    discovered: list[DiscoveredTool] = []
    for server in servers:
        discovered.extend(await discover(server))
    return discovered
