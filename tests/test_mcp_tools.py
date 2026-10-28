"""Tests for MCP support against a tiny real stdio MCP server written into a temporary file.
They cover the JSON-RPC client (initialize, list, call, tool errors), registration as mcp__server__tool with
approval unless the server is trusted, skipping a server that cannot start, and the .aider-agent.json format.
No network or external package is involved.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from aider.coders.native_agent_config import AgentConfigError, MCPServerConfig, parse_config
from aider.coders.native_mcp_setup import register_mcp_tools, tool_name
from aider.native_mcp_client import MCPClient, MCPError
from aider.native_tool_calls import ToolCall
from aider.native_tool_context import DENIED_ACTION, ToolContext, ToolPermission
from aider.native_toolcalling import NativeToolRegistry

FAKE_SERVER = r'''
import json, sys
TOOLS = [{"name": "shout", "description": "Upper-case text",
          "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
         {"name": "fail", "description": "Always fails", "inputSchema": {"type": "object", "properties": {}}}]
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    method, params = msg["method"], msg.get("params", {})
    if method == "initialize":
        result = {"protocolVersion": params["protocolVersion"], "capabilities": {"tools": {}},
                  "serverInfo": {"name": "fake", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif params.get("name") == "shout":
        result = {"content": [{"type": "text", "text": params["arguments"]["text"].upper()}]}
    else:
        result = {"content": [{"type": "text", "text": "it broke"}], "isError": True}
    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)
'''


class MCPTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.script = Path(self.tmp.name, "server.py")
        self.script.write_text(FAKE_SERVER)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def server(self, trusted: bool, command: tuple = ()) -> MCPServerConfig:
        return MCPServerConfig("fake", command or (sys.executable, str(self.script)), (), trusted)

    def context(self, answer: bool, asked: list) -> ToolContext:
        return ToolContext(Path(self.tmp.name), list, lambda a, r: [],
                           lambda p, t, d: asked.append(p) or answer, lambda p: None, False)

    def test_client(self) -> None:
        client = MCPClient([sys.executable, str(self.script)], None, self.tmp.name)
        try:
            client.initialize()
            self.assertEqual([t.name for t in client.list_tools()], ["shout", "fail"])
            self.assertEqual(client.call_tool("shout", {"text": "hi"}), "HI")
            with self.assertRaises(MCPError):
                client.call_tool("fail", {})
        finally:
            client.close()

    def test_registered_tools_ask_unless_trusted(self) -> None:
        for trusted, answer, expected in ((False, True, "HI"), (False, False, DENIED_ACTION), (True, False, "HI")):
            with self.subTest(trusted=trusted, answer=answer):
                registry, asked = NativeToolRegistry(), []
                clients = register_mcp_tools(registry, self.context(answer, asked), (self.server(trusted),), print)
                try:
                    name = tool_name("fake", "shout")
                    self.assertIn(name, [s["function"]["name"] for s in registry.schemas()])
                    result = registry.execute(ToolCall("c1", name, json.dumps({"text": "hi"})))
                    self.assertEqual(result.content, expected)
                    self.assertEqual(asked, [] if trusted else [ToolPermission.MCP])
                finally:
                    for client in clients:
                        client.close()

    def test_broken_server_is_skipped_with_a_warning(self) -> None:
        warnings, registry = [], NativeToolRegistry()
        clients = register_mcp_tools(registry, self.context(True, []),
                                     (self.server(False, ("/nonexistent/mcp-server",)),), warnings.append)
        self.assertEqual((clients, registry.schemas()), ([], []))
        self.assertIn("could not start", warnings[0])

    def test_tool_names_are_sanitized(self) -> None:
        self.assertEqual(tool_name("my server", "do.it"), "mcp__my_server__do_it")
        self.assertLessEqual(len(tool_name("s" * 50, "t" * 50)), 64)

    def test_config(self) -> None:
        config = parse_config({"mcp_servers": {"docs": {"command": "npx", "args": ["-y", "srv"],
                                                        "env": {"K": "v"}, "trusted": True}}})
        self.assertEqual(config.mcp_servers, (MCPServerConfig("docs", ("npx", "-y", "srv"), (("K", "v"),), True),))
        for bad in ({"mcp_servers": []}, {"mcp_servers": {"x": {}}}, {"mcp_servers": {"x": {"command": "a", "args": "b"}}}):
            with self.subTest(bad=bad), self.assertRaises(AgentConfigError):
                parse_config(bad)


if __name__ == "__main__":
    unittest.main()
