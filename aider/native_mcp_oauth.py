"""Pure pieces of the MCP OAuth flow (authorization code with PKCE), as the MCP authorization spec describes it.
They derive the discovery URLs (protected resource metadata, RFC 9728; authorization server metadata, RFC 8414),
build the PKCE pair and the authorization URL with the resource indicator (RFC 8707), and parse redirects.
TokenSet holds what a token endpoint returned and knows when it expires; nothing here does network or file I/O.
"""

import base64
import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlsplit

from aider.native_mcp_client import MCPError

PROTECTED_RESOURCE_PATH = "/.well-known/oauth-protected-resource"
AUTH_SERVER_PATHS = ("/.well-known/oauth-authorization-server", "/.well-known/openid-configuration")
RESOURCE_METADATA_PARAM = re.compile(r'resource_metadata="([^"]+)"')
SCOPE_PARAM = re.compile(r'(?<![A-Za-z_])scope="([^"]*)"')
CHALLENGE_METHOD = "S256"
RESPONSE_TYPE = "code"
EXPIRY_MARGIN_SECONDS = 60
NO_EXPIRY = 0.0


class MCPAuthError(MCPError):
    """Raised when an MCP server's OAuth flow cannot complete."""


ANY_PORT = 0


@dataclass(frozen=True)
class OAuthSettings:
    """A server's "oauth" config. Defaults: register a client dynamically, no scope, any free callback port."""

    client_id: str = ""
    scope: str = ""
    callback_port: int = ANY_PORT


def origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def resource_metadata_urls(server_url: str, www_authenticate: str) -> list[str]:
    """Where to look for the protected resource metadata: the 401 header's hint, then the well-known locations."""
    hinted = RESOURCE_METADATA_PARAM.search(www_authenticate or "")
    path = urlsplit(server_url).path.rstrip("/")
    urls = [hinted.group(1)] if hinted else []
    if path:
        urls.append(origin(server_url) + PROTECTED_RESOURCE_PATH + path)
    urls.append(origin(server_url) + PROTECTED_RESOURCE_PATH)
    return urls


def challenge_scope(www_authenticate: str, configured: str) -> str:
    """The configured scope, else the one the server's 401 asks for, else none."""
    if configured:
        return configured
    match = SCOPE_PARAM.search(www_authenticate or "")
    return match.group(1) if match else ""


def auth_server_metadata_urls(issuer: str) -> list[str]:
    """RFC 8414 locations for an issuer, with the issuer's path inserted after the well-known segment."""
    path = urlsplit(issuer).path.rstrip("/")
    return [origin(issuer) + well_known + path for well_known in AUTH_SERVER_PATHS]


def pkce_pair(random_bytes: bytes) -> tuple[str, str]:
    """(code_verifier, S256 code_challenge) from at least 32 random bytes."""
    verifier = base64.urlsafe_b64encode(random_bytes).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def authorize_url(endpoint: str, client_id: str, redirect_uri: str, challenge: str, state: str, resource: str,
                  scope: str) -> str:
    params = {"response_type": RESPONSE_TYPE, "client_id": client_id, "redirect_uri": redirect_uri,
              "code_challenge": challenge, "code_challenge_method": CHALLENGE_METHOD, "state": state,
              "resource": resource}
    if scope:
        params["scope"] = scope
    return endpoint + ("&" if "?" in endpoint else "?") + urlencode(params)


def redirect_code(query: str, state: str) -> str:
    """The authorization code from the redirect's query string; raises on an error or a state mismatch."""
    params = {name: values[0] for name, values in parse_qs(query).items()}
    if "error" in params:
        raise MCPAuthError(f"Authorization refused: {params['error']} {params.get('error_description', '')}".strip())
    if params.get("state") != state:
        raise MCPAuthError("Authorization redirect had the wrong state; try again.")
    if not params.get("code"):
        raise MCPAuthError("Authorization redirect had no code.")
    return params["code"]


@dataclass(frozen=True)
class TokenSet:
    """Tokens for one server, with the client they were issued to; expires_at 0 means no known expiry."""

    access_token: str
    refresh_token: str
    expires_at: float
    client_id: str
    token_endpoint: str

    def expired(self, now: float) -> bool:
        return self.expires_at != NO_EXPIRY and now >= self.expires_at - EXPIRY_MARGIN_SECONDS

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def token_set(response: dict[str, Any], now: float, client_id: str, token_endpoint: str,
              previous: Optional[TokenSet] = None) -> TokenSet:
    """A TokenSet from a token response; a refresh response may omit the refresh token, which is then kept."""
    access = response.get("access_token")
    if not isinstance(access, str) or not access:
        raise MCPAuthError(f"Token endpoint returned no access_token: {response.get('error', response)}")
    expires_in = response.get("expires_in")
    expires_at = now + float(expires_in) if isinstance(expires_in, (int, float)) else NO_EXPIRY
    refresh = response.get("refresh_token") or (previous.refresh_token if previous else "")
    return TokenSet(access, refresh, expires_at, client_id, token_endpoint)


def parse_token_set(raw: Any) -> Optional[TokenSet]:
    """A stored TokenSet, or None when the stored value is not one."""
    try:
        return TokenSet(**raw)
    except TypeError:
        return None
