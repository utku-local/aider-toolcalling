"""The web_search tool: queries the search service the project configures and returns titles, URLs and snippets.
The service is a URL template with {query} that answers in SearXNG's JSON format (results with title, url and
content), for example a SearXNG instance run on this machine; without one the tool says search is not set up.
A search is asked unless the project allows searches, because the query leaves the machine.
"""

import json
from urllib.parse import quote_plus

from aider.native_tool_context import DENIED_ACTION, ToolContext, ToolPermission
from aider.native_toolcalling import NativeToolError, NativeToolRegistry
from aider.native_tools_fetch import UNTRUSTED_NOTE, download

QUERY_FIELD = "{query}"
DEFAULT_RESULTS = 8
MAX_RESULTS = 15
NO_RESULTS = "No results."
NOT_SET_UP = (
    "Web search is not set up for this project. Tell the user it needs \"network\": {\"search_url\": "
    "\"http://127.0.0.1:8888/search?q={query}&format=json\"} in .aider-agent.json or the same URL in the "
    "AIDER_AGENT_SEARCH_URL environment variable (a SearXNG instance), or use fetch_url on a documentation URL "
    "you know."
)
SEARCH_PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "max_results": {"type": "integer", "description": f"Results to return (default {DEFAULT_RESULTS})."},
    },
    "required": ["query"],
}


class SearchError(NativeToolError):
    """Raised for an empty query or a reply that is not search results."""


def parse_results(body: str, limit: int) -> list[tuple[str, str, str]]:
    """(title, url, snippet) from a SearXNG-style JSON reply."""
    try:
        results = json.loads(body).get("results", [])
    except (ValueError, AttributeError) as err:
        raise SearchError(f"The search service did not return JSON results: {err}") from err
    found = [(" ".join(str(r.get("title", "")).split()), str(r.get("url", "")), " ".join(str(r.get("content", "")).split()))
             for r in results if isinstance(r, dict) and r.get("url")]
    return found[:limit]


def format_results(results: list[tuple[str, str, str]]) -> str:
    if not results:
        return NO_RESULTS
    return "\n\n".join(f"{n}. {title}\n   {url}\n   {snippet}" for n, (title, url, snippet) in enumerate(results, 1))


def web_search(ctx: ToolContext, query: str, max_results: int = DEFAULT_RESULTS) -> str:
    if not query.strip():
        raise SearchError("query must not be empty")
    if not ctx.web.search_url:
        return NOT_SET_UP
    if not ctx.web.search and not ctx.approve(ToolPermission.NETWORK, "Search the web?", query):
        return DENIED_ACTION
    _, _, body = download(ctx.web.search_url.replace(QUERY_FIELD, quote_plus(query)))
    limit = max(1, min(int(max_results), MAX_RESULTS))
    return f"{UNTRUSTED_NOTE}\nSearch: {query}\n\n{format_results(parse_results(body, limit))}"


def register_search_web_tool(registry: NativeToolRegistry, ctx: ToolContext) -> None:
    registry.register(
        "web_search",
        "Search the web; returns titles, URLs and snippets. Read a result with fetch_url.",
        SEARCH_PARAMETERS,
        lambda query, max_results=DEFAULT_RESULTS: web_search(ctx, query, max_results),
    )
