"""Starts the MCP servers listed in .aider-agent.json and registers their tools on the agent's registry.
Each tool is exposed as mcp__<server>__<tool> with the server's input schema; a call asks the user first unless
the server is marked trusted, because an MCP tool can do anything its server can.
A server that fails to start is reported once and skipped, and every started server is closed when Aider exits.
"""

import atexit
import json
import os
import re
from typing import Any

from aider.native_mcp_client import MCPClient, MCPTool
from aider.native_tool_context import DENIED_ACTION, ToolContext, ToolPermission
from aider.native_toolcalling import NativeToolRegistry

from .native_agent_config import MCPServerConfig

TOOL_PREFIX = "mcp__"
NAME_SEPARATOR = "__"
UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9_-]")
MAX_TOOL_NAME = 64
OBJECT_SCHEMA = {"type": "object", "properties": {}}


def tool_name(server: str, tool: str) -> str:
    """OpenAI-compatible tool name: letters, digits, _ and -, at most 64 characters."""
    name = TOOL_PREFIX + UNSAFE_NAME_CHARS.sub("_", server) + NAME_SEPARATOR + UNSAFE_NAME_CHARS.sub("_", tool)
    return name[:MAX_TOOL_NAME]


def object_schema(schema: dict[str, Any]) -> dict[str, Any]:
    return schema if schema.get("type") == "object" else dict(OBJECT_SCHEMA)


def call_mcp(ctx: ToolContext, server: MCPServerConfig, client: MCPClient, tool: MCPTool, **arguments: Any) -> str:
    if not server.trusted and not ctx.approve(
        ToolPermission.MCP, f"Call MCP tool {server.name}/{tool.name}?", json.dumps(arguments, indent=2)
    ):
        return DENIED_ACTION
    return client.call_tool(tool.name, arguments)


def start_server(server: MCPServerConfig, cwd: str) -> MCPClient:
    client = MCPClient(list(server.command), {**os.environ, **dict(server.env)}, cwd)
    try:
        client.initialize()
    except Exception:
        client.close()
        raise
    atexit.register(client.close)
    return client


def register_mcp_tools(
    registry: NativeToolRegistry, ctx: ToolContext, servers: tuple[MCPServerConfig, ...], warn: Any
) -> list[MCPClient]:
    """Start each server and register its tools; returns the running clients."""
    clients = []
    for server in servers:
        try:
            client = start_server(server, str(ctx.root))
            tools = client.list_tools()
        except Exception as err:  # a broken server must not stop the agent
            warn(f"MCP server {server.name!r} could not start: {err}")
            continue
        clients.append(client)
        for tool in tools:
            registry.register(
                tool_name(server.name, tool.name),
                tool.description or f"{tool.name} from MCP server {server.name}",
                object_schema(tool.input_schema),
                lambda _s=server, _c=client, _t=tool, **arguments: call_mcp(ctx, _s, _c, _t, **arguments),
            )
    return clients
