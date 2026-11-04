"""Tests for the no-matches hint that search_code adds for a fruitless def/class search.
They cover the pure definition_search_hint helper (name extraction past regex whitespace, def vs class, non-matches)
and the search_code integration where searching for a function that is really an attribute returns the hint while a
real definition does not. The integration uses a temporary repo and a plain ToolContext; no model is needed.
"""

import tempfile
import unittest
from pathlib import Path

from aider.native_tool_context import ToolContext
from aider.native_tools_search import NO_RESULTS, definition_search_hint, search_code


def ctx_for(root: Path, files: list[str]) -> ToolContext:
    return ToolContext(root, lambda: files, lambda a, r: [], lambda p, t, d: True, lambda p: None, False)


class DefinitionSearchHintTest(unittest.TestCase):
    def test_def_search_names_the_symbol_and_suggests_alternatives(self) -> None:
        hint = definition_search_hint("def root(")
        self.assertIn("root", hint)
        self.assertIn("find_symbol", hint)
        self.assertIn("root =", hint)

    def test_regex_whitespace_between_keyword_and_name_is_skipped(self) -> None:
        self.assertIn("root", definition_search_hint(r"def\s+root"))
        self.assertNotIn(" s ", definition_search_hint(r"def\s+root"))

    def test_async_def_is_recognized(self) -> None:
        self.assertIn("handler", definition_search_hint("async def handler("))

    def test_class_search_uses_the_class_phrasing(self) -> None:
        hint = definition_search_hint("class Config")
        self.assertIn("Config", hint)
        self.assertIn("find_symbol", hint)
        self.assertIn("without `class`", hint)

    def test_non_definition_patterns_get_no_hint(self) -> None:
        for pattern in ("root", "API_KEY", "self.root =", "define_foo", "def "):
            with self.subTest(pattern=pattern):
                self.assertEqual(definition_search_hint(pattern), "")


class SearchCodeHintTest(unittest.TestCase):
    def test_attribute_searched_as_def_returns_the_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "mod.py").write_text("class Config:\n    def __init__(self):\n        self.root = '/x'\n")
            ctx = ctx_for(root, ["mod.py"])
            result = search_code(ctx, "def root")
            self.assertTrue(result.startswith(NO_RESULTS))
            self.assertIn("root =", result)

    def test_real_definition_match_has_no_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "mod.py").write_text("class Config:\n    def __init__(self):\n        self.root = '/x'\n")
            ctx = ctx_for(root, ["mod.py"])
            result = search_code(ctx, "def __init__")
            self.assertIn("mod.py:2:", result)
            self.assertNotIn("find_symbol", result)

    def test_non_definition_miss_stays_plain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "mod.py").write_text("x = 1\n")
            ctx = ctx_for(root, ["mod.py"])
            self.assertEqual(search_code(ctx, "nonexistent_token"), NO_RESULTS)


if __name__ == "__main__":
    unittest.main()
