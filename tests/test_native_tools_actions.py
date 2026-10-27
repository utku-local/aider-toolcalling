"""Tests for the search, edit and shell tools against a temporary project directory.
A ToolContext built from plain functions records approvals and edits, so no Aider io or model is involved.
They cover result formats, the exact-match edit rules, approval denial, dry runs and command timeouts.
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from aider.native_tool_context import ToolContext, ToolPermission
from aider.native_tools_builtin import read_file
from aider.native_tools_edit import DENIED_MESSAGE, EditError, edit_file, replace_text, write_file
from aider.native_tools_search import NO_RESULTS, SearchError, find_files, find_symbol, search_code
from aider.native_tools_shell import run_command

FILES = {
    "src/app.py": "def main():\n    return helper()\n\n\ndef helper():\n    return 42\n",
    "src/util.py": "VALUE = 1\nvalue = 2\n",
    "README.md": "# Demo\n",
}


class Recorder:
    """Approval and edit callbacks with a fixed answer."""

    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.asked: list[tuple[ToolPermission, str, str]] = []
        self.edited: list[str] = []

    def approve(self, permission: ToolPermission, title: str, details: str) -> bool:
        self.asked.append((permission, title, details))
        return self.answer


def fake_tags(abs_path: str, rel_path: str) -> list[Any]:
    if rel_path != "src/app.py":
        return []
    return [
        SimpleNamespace(kind="def", name="helper", line=4),
        SimpleNamespace(kind="def", name="helper", line=4),
        SimpleNamespace(kind="ref", name="helper", line=1),
    ]


class ActionToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        for rel, text in FILES.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def ctx(self, answer: bool = True, dry_run: bool = False) -> tuple[ToolContext, Recorder]:
        recorder = Recorder(answer)
        context = ToolContext(
            root=self.root,
            list_files=lambda: sorted(FILES),
            find_tags=fake_tags,
            approve=recorder.approve,
            on_edit=recorder.edited.append,
            dry_run=dry_run,
        )
        return context, recorder

    def test_find_files(self) -> None:
        ctx, _ = self.ctx()
        self.assertEqual(find_files(ctx, "*.py"), "src/app.py\nsrc/util.py")
        self.assertEqual(find_files(ctx, "*.rs"), NO_RESULTS)

    def test_search_code(self) -> None:
        ctx, _ = self.ctx()
        self.assertEqual(search_code(ctx, r"return \d+"), "src/app.py:6: return 42")
        self.assertEqual(search_code(ctx, "^value", "src/*", ignore_case=True).count("\n"), 1)
        with self.assertRaises(SearchError):
            search_code(ctx, "(")

    def test_find_symbol_reports_definitions_only(self) -> None:
        ctx, _ = self.ctx()
        self.assertEqual(find_symbol(ctx, "helper"), "src/app.py:5: helper")
        self.assertEqual(find_symbol(ctx, "missing"), NO_RESULTS)

    def test_read_file_line_range(self) -> None:
        self.assertEqual(read_file(self.root, "src/app.py", 5, 6), "def helper():\n    return 42\n")
        self.assertEqual(read_file(self.root, "src/util.py", end_line=1), "VALUE = 1\n")

    def test_replace_text_rules(self) -> None:
        self.assertEqual(replace_text("a b a", "b", "c", False), ("a c a", 1))
        self.assertEqual(replace_text("a b a", "a", "x", True), ("x b x", 2))
        for old, replace_all in (("a", False), ("zz", False), ("", True)):
            with self.subTest(old=old), self.assertRaises(EditError):
                replace_text("a b a", old, "x", replace_all)

    def test_edit_file_asks_with_a_diff_and_records_the_edit(self) -> None:
        ctx, recorder = self.ctx()
        result = edit_file(ctx, "src/util.py", "VALUE = 1", "VALUE = 10")
        self.assertIn("1 replacement", result)
        self.assertIn("VALUE = 10", (self.root / "src/util.py").read_text())
        permission, _, diff = recorder.asked[0]
        self.assertIs(permission, ToolPermission.WRITE)
        self.assertIn("-VALUE = 1", diff)
        self.assertIn("+VALUE = 10", diff)
        self.assertEqual(recorder.edited, [str(self.root / "src/util.py")])

    def test_declined_and_dry_run_edits_do_not_write(self) -> None:
        for answer, dry_run in ((False, False), (True, True)):
            ctx, recorder = self.ctx(answer, dry_run)
            result = edit_file(ctx, "src/util.py", "VALUE = 1", "VALUE = 3")
            self.assertEqual((self.root / "src/util.py").read_text(), FILES["src/util.py"])
            self.assertEqual(recorder.edited, [])
            if not answer:
                self.assertEqual(result, DENIED_MESSAGE)

    def test_write_file_creates_and_overwrites_inside_root(self) -> None:
        ctx, recorder = self.ctx()
        self.assertTrue(write_file(ctx, "new/dir/x.txt", "hi\n").startswith("Created"))
        self.assertEqual((self.root / "new/dir/x.txt").read_text(), "hi\n")
        self.assertTrue(write_file(ctx, "README.md", "# New\n").startswith("Overwrote"))
        with self.assertRaises(Exception):
            write_file(ctx, "../escape.txt", "x")
        self.assertEqual(len(recorder.edited), 2)

    def test_run_command(self) -> None:
        ctx, recorder = self.ctx()
        result = run_command(ctx, "echo out; echo err 1>&2; exit 3")
        self.assertTrue(result.startswith("Exit code: 3"))
        self.assertIn("out", result)
        self.assertIn("err", result)
        self.assertIs(recorder.asked[0][0], ToolPermission.EXECUTE)
        self.assertIn("timed out", run_command(ctx, "sleep 5", timeout_seconds=1))

    def test_declined_command_does_not_run(self) -> None:
        ctx, _ = self.ctx(answer=False)
        self.assertEqual(run_command(ctx, "touch ran.txt"), DENIED_MESSAGE)
        self.assertFalse((self.root / "ran.txt").exists())


if __name__ == "__main__":
    unittest.main()
