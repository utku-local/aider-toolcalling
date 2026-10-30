"""Tests for MCP OAuth: the pure helpers and the whole sign-in flow against a local fake server.
The fake server is the MCP endpoint, its protected resource metadata, and an authorization server with dynamic
registration, an authorize endpoint that redirects straight back, and a token endpoint that checks PKCE.
The "browser" just follows the redirect, so the test covers discovery, registration, code exchange, reuse and refresh.
"""

import base64
import hashlib
import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlsplit

from aider.coders.native_agent_config import AgentConfigError, parse_config
from aider.native_mcp_http import MCPHttpClient
from aider.native_mcp_oauth import (
    MCPAuthError,
    OAuthSettings,
    TokenSet,
    auth_server_metadata_urls,
    challenge_scope,
    pkce_pair,
    redirect_code,
    resource_metadata_urls,
    token_set,
)
from aider.native_mcp_oauth_flow import OAuthProvider, TokenStore

RFC7636_BYTES = bytes([116, 24, 223, 180, 151, 153, 224, 37, 79, 250, 96, 125, 216, 173, 187, 186, 22, 212, 37, 77,
                       105, 214, 191, 240, 91, 88, 5, 88, 83, 132, 141, 121])
RFC7636_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC7636_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
BROWSER_TIMEOUT_SECONDS = 10


class FakeServer:
    """Shared state of the fake MCP and authorization server."""

    def __init__(self) -> None:
        self.valid_tokens: set[str] = set()
        self.challenges: dict[str, str] = {}
        self.registered: list[dict[str, Any]] = []
        self.resources: list[str] = []
        self.scopes: list[str] = []
        self.issued = 0

    def issue(self) -> dict[str, Any]:
        self.issued += 1
        token = f"access-{self.issued}"
        self.valid_tokens.add(token)
        return {"access_token": token, "refresh_token": f"refresh-{self.issued}", "expires_in": 3600}


class FakeHandler(BaseHTTPRequestHandler):
    """Serves the fake endpoints; `state` and `base` are set on a subclass per test."""

    state: FakeServer
    base: list[str]

    def reply(self, code: int, body: Any, headers: Optional[dict[str, str]] = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        if parts.path == "/.well-known/oauth-protected-resource/mcp":
            self.reply(200, {"resource": self.base[0] + "/mcp", "authorization_servers": [self.base[0]]})
        elif parts.path == "/.well-known/oauth-authorization-server":
            self.reply(200, {"authorization_endpoint": self.base[0] + "/authorize", "token_endpoint": self.base[0] + "/token",
                             "registration_endpoint": self.base[0] + "/register"})
        elif parts.path == "/authorize":
            query = {k: v[0] for k, v in parse_qs(parts.query).items()}
            self.state.challenges["code-1"] = query["code_challenge"]
            self.state.resources.append(query["resource"])
            self.state.scopes.append(query.get("scope", ""))
            target = query["redirect_uri"] + "?" + urlencode({"code": "code-1", "state": query["state"]})
            self.send_response(302)
            self.send_header("Location", target)
            self.end_headers()
        else:
            self.reply(404, {})

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        path = urlsplit(self.path).path
        if path == "/register":
            self.state.registered.append(json.loads(body))
            self.reply(201, {"client_id": "client-1"})
        elif path == "/token":
            self.token(dict(parse_qs(body)))
        elif self.headers.get("Authorization", "").removeprefix("Bearer ") not in self.state.valid_tokens:
            metadata = (f'Bearer resource_metadata="{self.base[0]}/.well-known/oauth-protected-resource/mcp", '
                        'scope="tools"')
            self.reply(401, {}, {"WWW-Authenticate": metadata})
        else:
            self.mcp(json.loads(body))

    def token(self, form: dict[str, list[str]]) -> None:
        if form["grant_type"] == ["refresh_token"]:
            self.reply(200, self.state.issue())
            return
        digest = hashlib.sha256(form["code_verifier"][0].encode()).digest()
        if base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != self.state.challenges.get(form["code"][0]):
            self.reply(400, {"error": "invalid_grant"})
            return
        self.reply(200, self.state.issue())

    def mcp(self, message: dict[str, Any]) -> None:
        if "id" not in message:
            self.reply(202, {})
            return
        result = {"tools": [{"name": "whoami", "inputSchema": {"type": "object"}}]} \
            if message["method"] == "tools/list" else {"protocolVersion": "2025-06-18"}
        self.reply(200, {"jsonrpc": "2.0", "id": message["id"], "result": result})

    def log_message(self, *args: object) -> None:
        """Keep test output quiet."""


def handler_for(state: FakeServer, base: list[str]) -> type:
    return type("Handler", (FakeHandler,), {"state": state, "base": base})


def follow(url: str) -> None:
    urllib.request.urlopen(url, timeout=BROWSER_TIMEOUT_SECONDS).read()


def no_browser(url: str) -> None:
    raise AssertionError(f"the browser should not open: {url}")


class OAuthFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = FakeServer()
        base: list[str] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.state, base))
        base.append(f"http://127.0.0.1:{self.server.server_port}")
        self.url = base[0] + "/mcp"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.tmp = tempfile.TemporaryDirectory()
        self.store = TokenStore(Path(self.tmp.name) / "tokens.json")

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def client(self, browser: Any) -> MCPHttpClient:
        return MCPHttpClient(self.url, {}, OAuthProvider(self.url, OAuthSettings(), self.store, browser))

    def test_sign_in_then_reuse_then_refresh(self) -> None:
        first = self.client(follow)
        first.initialize()
        self.assertEqual([t.name for t in first.list_tools()], ["whoami"])
        self.assertEqual(self.state.registered[0]["token_endpoint_auth_method"], "none")
        self.assertEqual(self.state.resources, [self.url])
        self.assertEqual(self.state.scopes, ["tools"])
        self.assertEqual(self.store.get(self.url).access_token, "access-1")
        self.assertEqual(oct(self.store.path.stat().st_mode & 0o777), "0o600")

        self.client(no_browser).initialize()
        self.state.valid_tokens.clear()
        self.client(no_browser).initialize()
        self.assertEqual(self.store.get(self.url).access_token, "access-2")
        self.assertEqual(len(self.state.registered), 1)


class OAuthHelperTest(unittest.TestCase):
    def test_pkce_matches_rfc_7636(self) -> None:
        self.assertEqual(pkce_pair(RFC7636_BYTES), (RFC7636_VERIFIER, RFC7636_CHALLENGE))

    def test_discovery_urls(self) -> None:
        hinted = 'Bearer resource_metadata="https://x.dev/meta"'
        self.assertEqual(resource_metadata_urls("https://x.dev/mcp", hinted),
                         ["https://x.dev/meta", "https://x.dev/.well-known/oauth-protected-resource/mcp",
                          "https://x.dev/.well-known/oauth-protected-resource"])
        self.assertEqual(auth_server_metadata_urls("https://auth.dev/tenant"),
                         ["https://auth.dev/.well-known/oauth-authorization-server/tenant",
                          "https://auth.dev/.well-known/openid-configuration/tenant"])

    def test_scope_from_the_challenge(self) -> None:
        challenge = 'Bearer realm="OAuth", resource_metadata="https://x.dev/m", scope="read write"'
        self.assertEqual(challenge_scope(challenge, ""), "read write")
        self.assertEqual(challenge_scope(challenge, "admin"), "admin")
        self.assertEqual(challenge_scope('Bearer realm="OAuth"', ""), "")

    def test_redirect_and_tokens(self) -> None:
        self.assertEqual(redirect_code("code=c&state=s", "s"), "c")
        for query in ("code=c&state=other", "error=access_denied&state=s", "state=s"):
            with self.assertRaises(MCPAuthError):
                redirect_code(query, "s")
        old = TokenSet("a", "r", 0.0, "client", "https://auth.dev/token")
        fresh = token_set({"access_token": "b", "expires_in": 100}, 1000.0, "client", old.token_endpoint, old)
        self.assertEqual((fresh.refresh_token, fresh.expires_at), ("r", 1100.0))
        self.assertFalse(old.expired(10**12))
        self.assertTrue(fresh.expired(1050.0))
        with self.assertRaises(MCPAuthError):
            token_set({"error": "invalid_grant"}, 0.0, "client", old.token_endpoint)

    def test_config(self) -> None:
        url = "https://mcp.example.com/mcp"
        self.assertEqual(parse_config({"mcp_servers": {"a": {"url": url, "oauth": True}}}).mcp_servers[0].oauth,
                         OAuthSettings())
        custom = {"client_id": "abc", "scope": "read", "callback_port": 8765}
        self.assertEqual(parse_config({"mcp_servers": {"a": {"url": url, "oauth": custom}}}).mcp_servers[0].oauth,
                         OAuthSettings("abc", "read", 8765))
        self.assertIsNone(parse_config({"mcp_servers": {"a": {"url": url}}}).mcp_servers[0].oauth)
        with self.assertRaises(AgentConfigError):
            parse_config({"mcp_servers": {"a": {"url": url, "oauth": {"secret": "x"}}}})
