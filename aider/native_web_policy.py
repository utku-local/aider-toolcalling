"""Which web requests the agent may make without asking: hosts on the project's allow list, and searches if enabled.
A pattern is an exact host ("pypi.org") or a wildcard for its subdomains ("*.readthedocs.io", which also matches
the bare domain); matching ignores case and a trailing dot.
Everything else still needs the user's approval, because a URL or a query can carry project data out.
"""

from dataclasses import dataclass
from urllib.parse import urlparse

WILDCARD = "*."


@dataclass(frozen=True)
class WebPolicy:
    """Defaults: no host is pre-approved, no search service is set up, and every search is asked."""

    allow_domains: tuple[str, ...] = ()
    search: bool = False
    search_url: str = ""


def normalize(host: str) -> str:
    return host.lower().rstrip(".")


def host_allowed(host: str, patterns: tuple[str, ...]) -> bool:
    name = normalize(host)
    for pattern in patterns:
        wanted = normalize(pattern)
        if wanted.startswith(WILDCARD):
            base = wanted[len(WILDCARD):]
            if name == base or name.endswith("." + base):
                return True
        elif name == wanted:
            return True
    return False


def url_allowed(url: str, policy: WebPolicy) -> bool:
    host = urlparse(url).hostname
    return bool(host) and host_allowed(host, policy.allow_domains)
