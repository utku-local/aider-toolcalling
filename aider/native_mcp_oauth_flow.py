"""The I/O side of MCP OAuth: discovery requests, client registration, the browser step and the token store.
OAuthProvider gives MCPHttpClient a bearer header, refreshes an expired token, and on a 401 runs the full flow:
discover the authorization server, register a client (or use a configured client_id), open the browser, catch the
redirect on a local port, exchange the code. Tokens are kept per server URL in ~/.aider-agent/mcp-oauth.json (0600).
"""

import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlencode, urlsplit

from aider.native_mcp_http import HttpAuth
from aider.native_mcp_oauth import (
    MCPAuthError,
    OAuthSettings,
    TokenSet,
    auth_server_metadata_urls,
    authorize_url,
    origin,
    parse_token_set,
    pkce_pair,
    redirect_code,
    resource_metadata_urls,
    token_set,
)

TOKEN_STORE = Path.home() / ".aider-agent" / "mcp-oauth.json"
TOKEN_STORE_MODE = 0o600
CALLBACK_HOST = "127.0.0.1"
CALLBACK_PATH = "/callback"
CALLBACK_TIMEOUT_SECONDS = 300
HTTP_TIMEOUT_SECONDS = 30
PKCE_BYTES = 32
STATE_BYTES = 16
CLIENT_NAME = "aider-toolcalling"
JSON_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}
FORM_HEADERS = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
DONE_PAGE = b"<html><body>Authorized. You can close this tab and return to the agent.</body></html>"


def http_json(url: str, data: Optional[bytes] = None, headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
    request = urllib.request.Request(url, data=data, headers=headers or {"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as reply:
            return json.loads(reply.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        raise MCPAuthError(f"{url} answered {err.code}: {body[:300]}") from err
    except (urllib.error.URLError, TimeoutError, ValueError) as err:
        raise MCPAuthError(f"{url} failed: {err}") from err


def first_json(urls: list[str]) -> dict[str, Any]:
    """The first of `urls` that returns a JSON object."""
    errors = []
    for url in urls:
        try:
            return http_json(url)
        except MCPAuthError as err:
            errors.append(str(err))
    raise MCPAuthError("OAuth discovery failed: " + "; ".join(errors))


class TokenStore:
    """Tokens by server URL in one JSON file, readable only by the user."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def get(self, server_url: str) -> Optional[TokenSet]:
        return parse_token_set(self.load().get(server_url))

    def put(self, server_url: str, tokens: TokenSet) -> None:
        data = self.load()
        data[server_url] = tokens.to_json()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.chmod(self.path, TOKEN_STORE_MODE)


def wait_for_redirect(server: HTTPServer, state: str) -> str:
    """Serve the local callback until the browser lands on it; returns the authorization code."""
    query: list[str] = []

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parts = urlsplit(self.path)
            if parts.path == CALLBACK_PATH:
                query.append(parts.query)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(DONE_PAGE)

        def log_message(self, *args: object) -> None:
            """Keep the agent's output clean."""

    server.RequestHandlerClass = Callback
    server.timeout = CALLBACK_TIMEOUT_SECONDS
    deadline = time.monotonic() + CALLBACK_TIMEOUT_SECONDS
    while not query and time.monotonic() < deadline:
        server.handle_request()
    server.server_close()
    if not query:
        raise MCPAuthError(f"No authorization within {CALLBACK_TIMEOUT_SECONDS} seconds.")
    return redirect_code(query[0], state)


def register_client(endpoint: str, redirect_uri: str) -> str:
    """Dynamic client registration (RFC 7591) as a public client; returns the client_id."""
    body = {"client_name": CLIENT_NAME, "redirect_uris": [redirect_uri], "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"]}
    client_id = http_json(endpoint, json.dumps(body).encode(), JSON_HEADERS).get("client_id")
    if not isinstance(client_id, str) or not client_id:
        raise MCPAuthError("Client registration returned no client_id.")
    return client_id


class OAuthProvider(HttpAuth):
    """Bearer tokens for one MCP server; `open_browser` shows the user the authorization URL."""

    def __init__(self, server_url: str, settings: OAuthSettings, store: TokenStore,
                 open_browser: Callable[[str], Any], clock: Callable[[], float] = time.time) -> None:
        self.server_url = server_url
        self.settings = settings
        self.store = store
        self.open_browser = open_browser
        self.clock = clock

    def headers(self) -> dict[str, str]:
        tokens = self.store.get(self.server_url)
        if tokens is not None and tokens.expired(self.clock()) and tokens.refresh_token:
            tokens = self.try_refresh(tokens)
        return {"Authorization": f"Bearer {tokens.access_token}"} if tokens else {}

    def unauthorized(self, challenge: str) -> None:
        """Called on a 401: refresh when possible, otherwise authorize in the browser."""
        tokens = self.store.get(self.server_url)
        if tokens is not None and tokens.refresh_token and self.try_refresh(tokens) is not None:
            return
        self.authorize(challenge)

    def try_refresh(self, tokens: TokenSet) -> Optional[TokenSet]:
        form = {"grant_type": "refresh_token", "refresh_token": tokens.refresh_token, "client_id": tokens.client_id,
                "resource": self.server_url}
        try:
            response = http_json(tokens.token_endpoint, urlencode(form).encode(), FORM_HEADERS)
        except MCPAuthError:
            return None
        fresh = token_set(response, self.clock(), tokens.client_id, tokens.token_endpoint, tokens)
        self.store.put(self.server_url, fresh)
        return fresh

    def discover(self, challenge: str) -> tuple[str, dict[str, Any]]:
        """(resource, authorization server metadata); servers without resource metadata use their own origin."""
        try:
            resource_meta = first_json(resource_metadata_urls(self.server_url, challenge))
        except MCPAuthError:
            resource_meta = {}
        issuers = resource_meta.get("authorization_servers") or [origin(self.server_url)]
        resource = resource_meta.get("resource") or self.server_url
        return resource, first_json(auth_server_metadata_urls(issuers[0]))

    def authorize(self, challenge: str) -> None:
        resource, meta = self.discover(challenge)
        callback = HTTPServer((CALLBACK_HOST, self.settings.callback_port), BaseHTTPRequestHandler)
        redirect_uri = f"http://{CALLBACK_HOST}:{callback.server_port}{CALLBACK_PATH}"
        try:
            client_id = self.settings.client_id or register_client(meta.get("registration_endpoint", ""),
                                                                   redirect_uri)
        except MCPAuthError:
            callback.server_close()
            raise
        verifier, code_challenge = pkce_pair(secrets.token_bytes(PKCE_BYTES))
        state = secrets.token_urlsafe(STATE_BYTES)
        url = authorize_url(meta["authorization_endpoint"], client_id, redirect_uri, code_challenge, state,
                            resource, self.settings.scope)
        threading.Thread(target=self.open_browser, args=(url,), daemon=True).start()
        code = wait_for_redirect(callback, state)
        form = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                "client_id": client_id, "code_verifier": verifier, "resource": resource}
        response = http_json(meta["token_endpoint"], urlencode(form).encode(), FORM_HEADERS)
        self.store.put(self.server_url, token_set(response, self.clock(), client_id, meta["token_endpoint"]))
