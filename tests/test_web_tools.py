"""Tests for the web allow list, the web_search parser and the "network" setting.
They check exact and wildcard host matching, that fetches and searches skip the approval only when allowed,
and that SearXNG-style JSON results are parsed and an unconfigured search says so.
No test touches the network: the download is replaced by a stub.
"""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from aider.coders.native_agent_config import AgentConfigError, parse_config, with_default_search
from aider.native_tool_context import DENIED_ACTION, ToolContext
from aider.native_tools_fetch import fetch_url
from aider.native_tools_websearch import NOT_SET_UP, SearchError, parse_results, web_search
from aider.native_web_policy import WebPolicy, host_allowed

RESULTS_PAGE = json.dumps({"results": [
    {"title": "tomllib  Parse TOML files", "url": "https://docs.python.org/3/library/tomllib.html",
     "content": "Read TOML with\n the standard library."},
    {"title": "Plain", "url": "https://example.org/plain"}, {"title": "no url"}]})
SEARCH_URL = "http://127.0.0.1:8888/search?q={query}&format=json"


def make_ctx(web: WebPolicy, approved: list) -> ToolContext:
    def approve(permission: object, title: str, details: str) -> bool:
        approved.append(details)
        return False

    return ToolContext(root=Path("."), list_files=lambda: [], find_tags=lambda a, b: [], approve=approve,
                       on_edit=lambda path: None, dry_run=False, web=web)


class HostTest(unittest.TestCase):
    def test_exact_and_wildcard_hosts(self) -> None:
        patterns = ("pypi.org", "*.readthedocs.io")
        self.assertTrue(host_allowed("PyPI.org.", patterns))
        self.assertTrue(host_allowed("requests.readthedocs.io", patterns))
        self.assertTrue(host_allowed("readthedocs.io", patterns))
        self.assertFalse(host_allowed("evil-pypi.org", patterns))
        self.assertFalse(host_allowed("readthedocs.io.evil.com", patterns))


class ApprovalTest(unittest.TestCase):
    def test_allowed_host_is_fetched_without_asking(self) -> None:
        asked: list = []
        ctx = make_ctx(WebPolicy(("docs.python.org",)), asked)
        with patch("aider.native_tools_fetch.download", return_value=(200, "text/plain", "hello")):
            self.assertIn("hello", fetch_url(ctx, "https://docs.python.org/3/"))
            self.assertEqual(fetch_url(ctx, "https://other.org/"), DENIED_ACTION)
        self.assertEqual(asked, ["https://other.org/"])

    def test_search_asks_unless_allowed(self) -> None:
        with patch("aider.native_tools_websearch.download", return_value=(200, "text/html", RESULTS_PAGE)):
            self.assertEqual(web_search(make_ctx(WebPolicy(), []), "toml"), NOT_SET_UP)
            self.assertEqual(web_search(make_ctx(WebPolicy(search_url=SEARCH_URL), []), "toml"), DENIED_ACTION)
            allowed = WebPolicy(search=True, search_url=SEARCH_URL)
            self.assertIn("docs.python.org", web_search(make_ctx(allowed, []), "toml"))


class ParserTest(unittest.TestCase):
    def test_titles_urls_and_snippets(self) -> None:
        results = parse_results(RESULTS_PAGE, 5)
        self.assertEqual(results[0], ("tomllib Parse TOML files", "https://docs.python.org/3/library/tomllib.html",
                                      "Read TOML with the standard library."))
        self.assertEqual(len(results), 2)
        self.assertEqual(len(parse_results(RESULTS_PAGE, 1)), 1)
        with self.assertRaises(SearchError):
            parse_results("<html>", 5)


class NetworkConfigTest(unittest.TestCase):
    def test_network_section(self) -> None:
        config = parse_config({"network": {"allow_domains": ["pypi.org"], "search": True, "search_url": SEARCH_URL}})
        self.assertEqual(config.web, WebPolicy(("pypi.org",), True, SEARCH_URL))
        with self.assertRaises(AgentConfigError):
            parse_config({"network": {"search_url": "http://x/search"}})
        self.assertEqual(parse_config({}).web, WebPolicy())
        with self.assertRaises(AgentConfigError):
            parse_config({"network": {"allow_domains": "pypi.org"}})

    def test_default_search_url_fills_only_an_unset_one(self) -> None:
        default = "http://127.0.0.1:8888/search?q={query}&format=json"
        self.assertEqual(with_default_search(parse_config({}), default).web.search_url, default)
        project = parse_config({"network": {"search_url": SEARCH_URL}})
        self.assertEqual(with_default_search(project, default).web.search_url, SEARCH_URL)
        self.assertEqual(with_default_search(parse_config({}), "http://x/search").web.search_url, "")
        self.assertEqual(with_default_search(parse_config({}), "").web.search_url, "")
