"""A minimal Model Context Protocol client — stdio and HTTP.

MCP is how a tool written by someone else becomes available here without
anyone writing an adapter for it: a server advertises its tools over JSON-RPC,
and we call them. The protocol surface we need is small — ``initialize``, the
``notifications/initialized`` acknowledgement, ``tools/list`` and
``tools/call`` — so this is a direct implementation rather than a dependency.

The part worth reading is how little the server is trusted.

An MCP server is **third-party code describing itself**. Its tool names,
descriptions and schemas are data that will end up inside a prompt, and its
outputs come back as tool results the model reads. So:

* a server never chooses its own permission tier — that comes from local
  configuration, and the default is Yellow (approval required), not Green;
* names are namespaced with the server's configured id, so two servers cannot
  collide and neither can shadow a built-in tool;
* every string that reaches a prompt is length-bounded here, at the boundary;
* one unreachable or misbehaving server is skipped, never fatal. A broken
  integration should cost its own tools and nothing else.

Descriptions are still attacker-influenced text: a hostile server can write a
description that argues for its own use. Tiering handles the consequence — a
Yellow tool cannot act without a human — which is why the tier is not the
server's to set.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
_CLIENT_INFO = {"name": "gummy-os", "version": "1.0"}

# Bounds applied to everything a server sends. A description is prompt text and
# a result is prompt text; neither may be unbounded.
MAX_DESCRIPTION_CHARS = 800
MAX_RESULT_CHARS = 20_000
MAX_TOOLS_PER_SERVER = 64

DEFAULT_TIMEOUT_SECONDS = 20.0
# A stdio server usually has to be installed on first run (npx downloads the
# package), so the handshake gets longer than a steady-state call.
HANDSHAKE_TIMEOUT_SECONDS = 90.0


class MCPError(RuntimeError):
    """The server was unreachable, spoke badly, or returned an error."""


@dataclass(frozen=True)
class MCPToolDefinition:
    """One tool as a server describes it, after bounding."""

    name: str
    description: str
    input_schema: dict


@dataclass
class StdioServer:
    """A server launched as a subprocess and spoken to over stdin/stdout."""

    command: str
    args: list[str] = field(default_factory=list)


@dataclass
class HttpServer:
    """A server reached over Streamable HTTP."""

    url: str
    token: str | None = None


class MCPClient:
    """One connection to one MCP server.

    Not reusable across servers and not thread-safe: create one, use it, close
    it. ``async with`` is the intended shape.
    """

    def __init__(self, transport: StdioServer | HttpServer, *, name: str) -> None:
        self._transport = transport
        self._name = name
        self._process: asyncio.subprocess.Process | None = None
        self._http: httpx.AsyncClient | None = None
        self._next_id = 0
        self._initialized = False

    async def __aenter__(self) -> MCPClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    # ── lifecycle ────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Start the transport and complete the MCP handshake."""
        if isinstance(self._transport, StdioServer):
            await self._start_process()
        else:
            headers = {"Content-Type": "application/json"}
            if self._transport.token:
                headers["Authorization"] = f"Bearer {self._transport.token}"
            self._http = httpx.AsyncClient(
                headers=headers, timeout=DEFAULT_TIMEOUT_SECONDS
            )

        await self._handshake()

    async def _start_process(self) -> None:
        assert isinstance(self._transport, StdioServer)
        try:
            self._process = await asyncio.create_subprocess_exec(
                self._transport.command,
                *self._transport.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except (OSError, ValueError) as exc:
            # On Windows an npm-installed launcher is a .cmd shim, which
            # exec cannot resolve from its bare name — the resulting
            # "file not found" says nothing useful on its own.
            raise MCPError(
                f"could not start {self._transport.command!r}: {exc}. "
                "On Windows, npm launchers need their .cmd suffix "
                "(npx.cmd, not npx)."
            ) from exc

    async def _handshake(self) -> None:
        result = await self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": _CLIENT_INFO,
            },
            timeout=HANDSHAKE_TIMEOUT_SECONDS,
        )
        if not isinstance(result, dict):
            raise MCPError("initialize returned a non-object result")
        await self._notify("notifications/initialized")
        self._initialized = True
        logger.info("mcp server %s initialized", self._name)

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None
        if self._process is not None:
            if self._process.returncode is None:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            self._process = None

    # ── protocol ─────────────────────────────────────────────────────────

    def _message_id(self) -> int:
        self._next_id += 1
        return self._next_id

    async def _request(
        self, method: str, params: dict, *, timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": self._message_id(),
            "method": method,
            "params": params,
        }
        if self._process is not None:
            response = await self._stdio_roundtrip(payload, timeout)
        elif self._http is not None:
            response = await self._http_roundtrip(payload, timeout)
        else:
            raise MCPError("client is not connected")

        if "error" in response:
            error = response["error"] or {}
            raise MCPError(f"{method} failed: {str(error.get('message', error))[:300]}")
        return response.get("result")

    async def _notify(self, method: str, params: dict | None = None) -> None:
        """Fire-and-forget: a notification has no id and expects no reply."""
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if self._process is not None and self._process.stdin is not None:
            self._process.stdin.write((json.dumps(payload) + "\n").encode())
            await self._process.stdin.drain()
        elif self._http is not None:
            assert isinstance(self._transport, HttpServer)
            await self._http.post(self._transport.url, json=payload)

    async def _stdio_roundtrip(self, payload: dict, timeout: float) -> dict:
        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            raise MCPError("stdio transport is not available")

        # Bound before the closure: the Optional narrowing on the guard above
        # does not propagate into a nested function.
        stdout = process.stdout
        process.stdin.write((json.dumps(payload) + "\n").encode())
        await process.stdin.drain()

        async def read_matching() -> dict:
            # Servers interleave notifications with responses, so read until
            # the id we sent comes back rather than taking the first line.
            while True:
                line = await stdout.readline()
                if not line:
                    raise MCPError("server closed the connection")
                try:
                    message = json.loads(line.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    continue
                if isinstance(message, dict) and message.get("id") == payload["id"]:
                    return message

        try:
            return await asyncio.wait_for(read_matching(), timeout=timeout)
        except TimeoutError:
            raise MCPError(
                f"{payload['method']} timed out after {timeout:.0f}s"
            ) from None

    async def _http_roundtrip(self, payload: dict, timeout: float) -> dict:
        assert isinstance(self._transport, HttpServer)
        assert self._http is not None
        try:
            response = await self._http.post(
                self._transport.url, json=payload, timeout=timeout
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MCPError(f"http transport failed: {type(exc).__name__}") from exc
        try:
            return response.json()
        except ValueError as exc:
            raise MCPError("server returned a non-JSON response") from exc

    # ── operations ───────────────────────────────────────────────────────

    async def list_tools(self) -> list[MCPToolDefinition]:
        """Discover the server's tools, bounded and normalised."""
        result = await self._request("tools/list", {})
        raw_tools = (result or {}).get("tools", [])
        if not isinstance(raw_tools, list):
            raise MCPError("tools/list did not return a list")

        tools: list[MCPToolDefinition] = []
        for raw in raw_tools[:MAX_TOOLS_PER_SERVER]:
            if not isinstance(raw, dict):
                continue
            name = raw.get("name")
            if not isinstance(name, str) or not name:
                continue
            schema = raw.get("inputSchema") or raw.get("input_schema") or {}
            if not isinstance(schema, dict):
                schema = {}
            tools.append(
                MCPToolDefinition(
                    name=name,
                    description=str(raw.get("description", ""))[:MAX_DESCRIPTION_CHARS],
                    input_schema=schema,
                )
            )
        return tools

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Invoke one tool and flatten its content blocks to text."""
        result = await self._request(
            "tools/call", {"name": name, "arguments": arguments}
        )
        result = result or {}

        # MCP returns a list of typed content blocks. Text is what a model can
        # use; other block types are summarised rather than dropped silently,
        # so an image result does not look like an empty one.
        parts: list[str] = []
        for block in result.get("content", []) or []:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "text":
                parts.append(str(block.get("text", "")))
            else:
                parts.append(f"[{kind or 'unknown'} content omitted]")

        text = "\n".join(parts)
        truncated = len(text) > MAX_RESULT_CHARS
        return {
            "content": text[:MAX_RESULT_CHARS],
            "truncated": truncated,
            # A server signals a tool-level failure in-band rather than as a
            # JSON-RPC error; surface it so the caller can distinguish.
            "is_error": bool(result.get("isError", False)),
        }
