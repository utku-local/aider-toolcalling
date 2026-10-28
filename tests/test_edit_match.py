"""Tests for edit_file matching, the trailing 2>&1 rule and the agent edit approval prompt.
They check that a block differing only in line-end whitespace is replaced in place, that a real mismatch names the
first differing line, and that exact matches behave as before.
They also check that a trailing 2>&1 no longer makes a command compound and that edit approvals offer no "don't ask".
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from aider.io import InputOutput
from aider.native_command_policy import CommandRules, PolicyAction, decide, without_stderr_merge
from aider.native_edit_match import find_spans, mismatch_hint
from aider.native_tools_edit import EditError, replace_text

SOURCE = "import os\nfrom fastapi import FastAPI   \nfrom sqlalchemy.orm import Session\n\napp = FastAPI()\n"


class EditMatchTest(unittest.TestCase):
    def test_exact_match_is_unchanged(self) -> None:
        after, count = replace_text(SOURCE, "import os\n", "import sys\n", False)
        self.assertEqual(count, 1)
        self.assertTrue(after.startswith("import sys\nfrom fastapi"))

    def test_line_end_whitespace_is_ignored(self) -> None:
        old = "from fastapi import FastAPI\nfrom sqlalchemy.orm import Session"
        new = "from fastapi import FastAPI\nfrom fastapi.staticfiles import StaticFiles\nfrom sqlalchemy.orm import Session"
        after, count = replace_text(SOURCE, old, new, False)
        self.assertEqual(count, 1)
        self.assertEqual(after, "import os\n" + new + "\n\napp = FastAPI()\n")

    def test_trailing_newline_of_old_string_is_kept(self) -> None:
        spans = find_spans(SOURCE, "from fastapi import FastAPI\n")
        self.assertEqual(SOURCE[spans[0][0]:spans[0][1]], "from fastapi import FastAPI   \n")

    def test_mismatch_names_the_first_differing_line(self) -> None:
        old = "from fastapi import FastAPI\nfrom sqlalchemy import Session"
        with self.assertRaises(EditError) as raised:
            replace_text(SOURCE, old, "x", False)
        self.assertIn("line 3 of the file is 'from sqlalchemy.orm import Session'", str(raised.exception))

    def test_unknown_first_line_has_no_hint(self) -> None:
        self.assertIsNone(mismatch_hint(SOURCE, "def missing():\n    pass"))
        with self.assertRaises(EditError) as raised:
            replace_text(SOURCE, "def missing():", "x", False)
        self.assertIn("first line does not occur", str(raised.exception))


class StderrMergeTest(unittest.TestCase):
    def test_trailing_stderr_merge_is_dropped(self) -> None:
        self.assertEqual(without_stderr_merge("pytest -q 2>&1"), "pytest -q")
        self.assertEqual(without_stderr_merge("pytest -q"), "pytest -q")

    def test_command_without_it_is_not_compound(self) -> None:
        rules = CommandRules()
        command = without_stderr_merge('python -c "import app" 2>&1')
        decision = decide(command, Path.cwd(), rules, sandboxed=True)
        self.assertEqual(decision.action, PolicyAction.ASK)
        self.assertFalse(decision.risks)


class EditPromptTest(unittest.TestCase):
    def test_group_prompt_can_drop_dont_ask_again(self) -> None:
        io = InputOutput(pretty=False)
        group = MagicMock(show_group=True, preference=None)
        asked: list[str] = []

        def answer(question: str) -> str:
            asked.append(question)
            return "y"

        with patch("builtins.input", side_effect=answer):
            io.prompt_session = None
            self.assertTrue(io.confirm_ask("Edit x?", group=group, allow_never=False))
            io.confirm_ask("Edit y?", group=group)
        self.assertNotIn("(D)on't ask again", asked[0])
        self.assertIn("(D)on't ask again", asked[1])
