"""Model Context Protocol support — third-party tools, locally tiered.

``client`` speaks the protocol; ``registry`` decides what a discovered tool is
allowed to do here. The split matters: the client trusts the server to be a
correct JSON-RPC peer, and nothing more.
"""

from app.services.mcp.client import (
    HttpServer,
    MCPClient,
    MCPError,
    MCPToolDefinition,
    StdioServer,
)
from app.services.mcp.registry import (
    TOOL_PREFIX,
    DiscoveredTool,
    MCPConfigError,
    MCPServerConfig,
    discover,
    discover_all,
    parse_config,
    tool_key,
)

__all__ = [
    "TOOL_PREFIX",
    "DiscoveredTool",
    "HttpServer",
    "MCPClient",
    "MCPConfigError",
    "MCPError",
    "MCPServerConfig",
    "MCPToolDefinition",
    "StdioServer",
    "discover",
    "discover_all",
    "parse_config",
    "tool_key",
]
