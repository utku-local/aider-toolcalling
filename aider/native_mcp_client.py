"""Minimal MCP client: the protocol steps shared by every transport, and the stdio transport.
MCPSession holds initialize, tools/list and tools/call over an abstract request; MCPClient runs a stdio server,
where MCP is newline-delimited JSON-RPC 2.0, so a subprocess with line reads and a reader thread is enough.
Every request has a timeout, and server errors become MCPError so the tool loop can report them to the model.
"""

import json
from abc import ABC, abstractmethod
import queue
import subprocess
import threading
from dataclasses import dataclass
from typing import Any, Optional

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "aider-toolcalling", "version": "1"}
REQUEST_TIMEOUT_SECONDS = 60
CLOSE_TIMEOUT_SECONDS = 5
JSONRPC_VERSION = "2.0"
TEXT_CONTENT = "text"


class MCPError(RuntimeError):
    """Raised when an MCP server fails, times out or returns an error."""


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]


class MCPSession(ABC):
    """The MCP steps above JSON-RPC; a transport provides request(method, params), notify(method) and close()."""

    @abstractmethod
    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and return its result."""

    @abstractmethod
    def notify(self, method: str) -> None:
        """Send a JSON-RPC notification."""

    @abstractmethod
    def close(self) -> None:
        """Release the transport."""

    def initialize(self) -> None:
        self.request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                    "clientInfo": CLIENT_INFO})
        self.notify("notifications/initialized")

    def list_tools(self) -> list[MCPTool]:
        tools = self.request("tools/list", {}).get("tools", [])
        return [
            MCPTool(t["name"], t.get("description", ""), t.get("inputSchema") or {"type": "object"})
            for t in tools if isinstance(t, dict) and isinstance(t.get("name"), str)
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        text = "\n".join(
            part.get("text", "") for part in result.get("content", []) if part.get("type") == TEXT_CONTENT
        )
        if result.get("isError"):
            raise MCPError(text or f"MCP tool {name} reported an error")
        return text


def response_result(method: str, message: dict[str, Any]) -> dict[str, Any]:
    """The result of a JSON-RPC response, or MCPError for an error response."""
    if "error" in message:
        raise MCPError(f"MCP {method} failed: {message['error'].get('message', message['error'])}")
    return message.get("result") or {}


class MCPClient(MCPSession):
    """One running stdio MCP server."""

    def __init__(self, command: list[str], env: Optional[dict[str, str]], cwd: str) -> None:
        self.process = subprocess.Popen(
            command, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        self.responses: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self.next_id = 0
        self.lock = threading.Lock()
        threading.Thread(target=self.read_loop, daemon=True).start()

    def read_loop(self) -> None:
        for line in self.process.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict) and "id" in message and ("result" in message or "error" in message):
                self.responses.put(message)

    def send(self, payload: dict[str, Any]) -> None:
        if self.process.poll() is not None:
            raise MCPError(f"MCP server exited with code {self.process.returncode}")
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            self.next_id += 1
            request_id = self.next_id
            self.send({"jsonrpc": JSONRPC_VERSION, "id": request_id, "method": method, "params": params})
            while True:
                try:
                    message = self.responses.get(timeout=REQUEST_TIMEOUT_SECONDS)
                except queue.Empty as err:
                    raise MCPError(f"MCP request {method} timed out") from err
                if message.get("id") == request_id:
                    break
        return response_result(method, message)

    def notify(self, method: str) -> None:
        self.send({"jsonrpc": JSONRPC_VERSION, "method": method})

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=CLOSE_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                self.process.kill()
