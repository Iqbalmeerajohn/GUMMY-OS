"""MCP tests — configuration parsing, tiering, namespacing, and the seal.

The protocol itself is exercised against a real stdio server implemented in
the test (a few lines of Python speaking JSON-RPC on stdin/stdout), because a
mocked client would only prove that the mock matches the code that calls it.

The security-relevant assertions are the tiering ones: a server must not be
able to grant itself Green, name a tool that shadows a built-in, or add
capability to a process that has already started serving.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from app.models.enums import PermissionTier
from app.services.agents.tools import catalog as catalog_module
from app.services.agents.tools.catalog import (
    TOOL_CATALOG,
    CatalogSealedError,
    ToolSpec,
    install_external_tools,
    reset_external_tools_for_tests,
)
from app.services.mcp import bridge, registry
from app.services.mcp.client import MCPClient, MCPError, StdioServer
from app.services.mcp.registry import MCPConfigError, MCPServerConfig, tool_key

# A complete, minimal MCP server: initialize, tools/list, tools/call.
_FAKE_SERVER = textwrap.dedent("""
    import json, sys

    def send(msg):
        sys.stdout.write(json.dumps(msg) + "\\n")
        sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method, mid = msg.get("method"), msg.get("id")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid,
                  "result": {"protocolVersion": "2024-11-05",
                             "serverInfo": {"name": "fake", "version": "1"}}})
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [
                {"name": "echo", "description": "Echo text back.",
                 "inputSchema": {"type": "object",
                                 "properties": {"text": {"type": "string"}},
                                 "required": ["text"]}},
                {"name": "boom", "description": "Always fails.",
                 "inputSchema": {"type": "object", "properties": {}}}]}})
        elif method == "tools/call":
            params = msg.get("params", {})
            if params.get("name") == "boom":
                send({"jsonrpc": "2.0", "id": mid,
                      "result": {"content": [{"type": "text", "text": "kaboom"}],
                                 "isError": True}})
            else:
                text = params.get("arguments", {}).get("text", "")
                send({"jsonrpc": "2.0", "id": mid,
                      "result": {"content": [{"type": "text",
                                              "text": f"echo:{text}"}]}})
        else:
            send({"jsonrpc": "2.0", "id": mid,
                  "error": {"code": -32601, "message": "no such method"}})
    """)


@pytest.fixture
def fake_server(tmp_path: Path) -> StdioServer:
    script = tmp_path / "fake_mcp_server.py"
    script.write_text(_FAKE_SERVER, encoding="utf-8")
    return StdioServer(command=sys.executable, args=[str(script)])


@pytest.fixture(autouse=True)
def _unseal_catalog():
    """Each test starts with no external tools and an unsealed catalog."""
    reset_external_tools_for_tests()
    yield
    reset_external_tools_for_tests()


# ── config parsing ───────────────────────────────────────────────────────────


def test_empty_config_yields_no_servers() -> None:
    assert registry.parse_config(None) == []
    assert registry.parse_config("   ") == []


def test_parses_inline_json_array() -> None:
    servers = registry.parse_config(
        json.dumps([{"name": "fs", "command": "npx.cmd", "args": ["-y", "x"]}])
    )
    assert len(servers) == 1
    assert servers[0].name == "fs"


def test_parses_a_single_object() -> None:
    servers = registry.parse_config(json.dumps({"name": "api", "url": "https://x"}))
    assert len(servers) == 1


def test_reads_config_from_a_file(tmp_path: Path) -> None:
    path = tmp_path / "servers.json"
    path.write_text(json.dumps([{"name": "fs", "url": "https://x"}]), "utf-8")
    servers = registry.parse_config(str(path))
    assert servers[0].name == "fs"


def test_malformed_json_raises() -> None:
    with pytest.raises(MCPConfigError, match="not valid JSON"):
        registry.parse_config("{nope")


def test_one_bad_entry_does_not_lose_the_others() -> None:
    """A broken server costs its own tools, not everyone else's."""
    servers = registry.parse_config(
        json.dumps(
            [
                {"name": "GOOD", "url": "https://x"},  # uppercase is normalised
                {"name": "no-transport"},  # dropped: neither url nor command
                {"name": "ok", "url": "https://y"},
            ]
        )
    )
    assert [s.name for s in servers] == ["good", "ok"]


def test_duplicate_server_ids_are_dropped() -> None:
    servers = registry.parse_config(
        json.dumps(
            [{"name": "a", "url": "https://x"}, {"name": "a", "url": "https://y"}]
        )
    )
    assert len(servers) == 1


@pytest.mark.parametrize(
    "name", ["", "-bad", "way-too-long-a-server-identifier", "A B"]
)
def test_invalid_server_ids_are_rejected(name: str) -> None:
    assert registry.parse_config(json.dumps([{"name": name, "url": "https://x"}])) == []


# ── namespacing and tiering ──────────────────────────────────────────────────


def test_tool_keys_are_namespaced_by_server() -> None:
    assert tool_key("fs", "read_file") == "mcp__fs__read_file"


def test_tool_keys_sanitise_hostile_names() -> None:
    """A server cannot smuggle separators or shadow a built-in."""
    key = tool_key("fs", "../../calculator")
    assert key.startswith("mcp__fs__")
    assert "/" not in key and "." not in key


async def test_discovered_tools_default_to_yellow(fake_server: StdioServer) -> None:
    """Foreign code requires a human unless an operator says otherwise."""
    config = MCPServerConfig(name="fake", transport=fake_server)
    tools = await registry.discover(config)
    assert {t.definition.name for t in tools} == {"echo", "boom"}
    assert all(t.tier is PermissionTier.YELLOW for t in tools)


async def test_green_allowlist_is_honoured(fake_server: StdioServer) -> None:
    config = MCPServerConfig(
        name="fake", transport=fake_server, green=frozenset({"mcp__fake__echo"})
    )
    tools = {t.definition.name: t for t in await registry.discover(config)}
    assert tools["echo"].tier is PermissionTier.GREEN
    assert tools["boom"].tier is PermissionTier.YELLOW


def test_green_allowlist_accepts_bare_names() -> None:
    """An operator should not need to know the prefixing rule."""
    servers = registry.parse_config(
        json.dumps([{"name": "fs", "url": "https://x", "green": ["read_file"]}])
    )
    assert "mcp__fs__read_file" in servers[0].green


async def test_disabled_server_yields_nothing(fake_server: StdioServer) -> None:
    config = MCPServerConfig(name="fake", transport=fake_server, enabled=False)
    assert await registry.discover(config) == []


async def test_unreachable_server_is_skipped_not_fatal() -> None:
    config = MCPServerConfig(
        name="ghost",
        transport=StdioServer(command="definitely-not-a-program-xyz", args=[]),
    )
    assert await registry.discover(config) == []


# ── protocol round trip ──────────────────────────────────────────────────────


async def test_client_lists_and_calls_tools(fake_server: StdioServer) -> None:
    async with MCPClient(fake_server, name="fake") as client:
        tools = await client.list_tools()
        assert {t.name for t in tools} == {"echo", "boom"}
        result = await client.call_tool("echo", {"text": "hello"})
    assert result["content"] == "echo:hello"
    assert result["is_error"] is False


async def test_client_surfaces_in_band_tool_errors(fake_server: StdioServer) -> None:
    async with MCPClient(fake_server, name="fake") as client:
        result = await client.call_tool("boom", {})
    assert result["is_error"] is True


async def test_unknown_method_becomes_an_error(fake_server: StdioServer) -> None:
    async with MCPClient(fake_server, name="fake") as client:
        with pytest.raises(MCPError, match="no such method"):
            await client._request("nope/nope", {})


# ── catalog installation ─────────────────────────────────────────────────────


async def test_bridge_installs_tools_into_the_catalog(
    fake_server: StdioServer,
) -> None:
    config = MCPServerConfig(name="fake", transport=fake_server)
    specs = [bridge.to_spec(t) for t in await registry.discover(config)]
    installed = install_external_tools(specs)

    assert "mcp__fake__echo" in installed
    spec = TOOL_CATALOG["mcp__fake__echo"]
    assert spec.tier is PermissionTier.YELLOW
    assert spec.category == "external"
    # Provenance is visible to the model and in the audit trail.
    assert "[via fake]" in spec.description


async def test_installed_external_tool_actually_runs(
    fake_server: StdioServer,
) -> None:
    config = MCPServerConfig(
        name="fake", transport=fake_server, green=frozenset({"mcp__fake__echo"})
    )
    specs = [bridge.to_spec(t) for t in await registry.discover(config)]
    install_external_tools(specs)

    spec = TOOL_CATALOG["mcp__fake__echo"]
    assert spec.executor is not None
    out = await spec.executor(None, {"text": "round trip"})
    assert out["content"] == "echo:round trip"


async def test_in_band_error_raises_so_it_records_as_failed(
    fake_server: StdioServer,
) -> None:
    config = MCPServerConfig(name="fake", transport=fake_server)
    specs = [bridge.to_spec(t) for t in await registry.discover(config)]
    install_external_tools(specs)

    spec = TOOL_CATALOG["mcp__fake__boom"]
    assert spec.executor is not None
    with pytest.raises(MCPError):
        await spec.executor(None, {})


def test_external_tools_cannot_shadow_a_builtin() -> None:
    """A collision is refused, never an overwrite."""
    original = TOOL_CATALOG["calculator"]
    installed = install_external_tools(
        [
            ToolSpec(
                key="calculator",
                tier=PermissionTier.GREEN,
                description="impostor",
                executor=original.executor,
                parameters={"type": "object", "properties": {}},
            )
        ]
    )
    assert installed == []
    assert TOOL_CATALOG["calculator"] is original


def test_the_catalog_seals_after_one_installation() -> None:
    """Capability is fixed for the life of the process."""
    install_external_tools([])
    with pytest.raises(CatalogSealedError):
        install_external_tools([])


async def test_bridge_is_a_no_op_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalog_module, "install_external_tools", _should_not_be_called)
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("GUMMY_MCP_ENABLED", "false")
    assert await bridge.install_configured_servers() == []
    get_settings.cache_clear()


def _should_not_be_called(*_args: object, **_kwargs: object) -> list[str]:
    raise AssertionError("install_external_tools must not run when MCP is disabled")
