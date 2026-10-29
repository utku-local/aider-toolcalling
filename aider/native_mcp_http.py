"""MCP over Streamable HTTP: each JSON-RPC message is a POST to the server's URL.
A reply is either a JSON body or a text/event-stream whose data lines carry JSON-RPC messages; the response with the
request's id is taken. The session id the server returns on initialize is sent with every later request.
Header values may name environment variables as ${NAME}, so API keys stay out of .aider-agent.json.
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from aider.native_mcp_client import (
    JSONRPC_VERSION,
    PROTOCOL_VERSION,
    REQUEST_TIMEOUT_SECONDS,
    MCPError,
    MCPSession,
    response_result,
)

SESSION_HEADER = "Mcp-Session-Id"
VERSION_HEADER = "MCP-Protocol-Version"
ACCEPT = "application/json, text/event-stream"
JSON_TYPE = "application/json"
EVENT_STREAM_TYPE = "text/event-stream"
DATA_PREFIX = "data:"
ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env(value: str, env: dict[str, str]) -> str:
    """Replace ${NAME} with the environment variable NAME (empty when it is not set)."""
    return ENV_REFERENCE.sub(lambda match: env.get(match.group(1), ""), value)


def messages_in(body: str, content_type: str) -> list[dict[str, Any]]:
    """The JSON-RPC messages in a reply body: one JSON value (object or batch) or the data lines of an event stream."""
    if EVENT_STREAM_TYPE in content_type:
        texts = [line[len(DATA_PREFIX):].strip() for line in body.splitlines() if line.startswith(DATA_PREFIX)]
    else:
        texts = [body]
    found: list[dict[str, Any]] = []
    for text in texts:
        if not text:
            continue
        try:
            value = json.loads(text)
        except ValueError:
            continue
        found.extend(v for v in (value if isinstance(value, list) else [value]) if isinstance(v, dict))
    return found


class MCPHttpClient(MCPSession):
    """One MCP server reached over HTTP."""

    def __init__(self, url: str, headers: dict[str, str]) -> None:
        self.url = url
        self.headers = {name: expand_env(value, dict(os.environ)) for name, value in headers.items()}
        self.session_id = ""
        self.next_id = 0

    def post(self, payload: dict[str, Any]) -> tuple[str, str]:
        headers = {"Content-Type": JSON_TYPE, "Accept": ACCEPT, VERSION_HEADER: PROTOCOL_VERSION, **self.headers}
        if self.session_id:
            headers[SESSION_HEADER] = self.session_id
        request = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as reply:
                self.session_id = reply.headers.get(SESSION_HEADER) or self.session_id
                return reply.read().decode("utf-8", errors="replace"), reply.headers.get_content_type()
        except (urllib.error.URLError, TimeoutError) as err:
            raise MCPError(f"MCP server {self.url} unreachable: {err}") from err

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.next_id += 1
        body, content_type = self.post({"jsonrpc": JSONRPC_VERSION, "id": self.next_id, "method": method,
                                        "params": params})
        for message in messages_in(body, content_type):
            if message.get("id") == self.next_id:
                return response_result(method, message)
        raise MCPError(f"MCP {method}: no response for request {self.next_id}")

    def notify(self, method: str) -> None:
        self.post({"jsonrpc": JSONRPC_VERSION, "method": method})

    def close(self) -> None:
        """Nothing to release: every request is its own HTTP exchange."""
