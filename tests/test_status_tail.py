"""Tests for dropping a trailing exit-status echo or `|| true`, and for separator echoes inside a command list.
The inputs are the commands Heretic and the 27B wrote in the expert eval runs of 2026-11-19.
Anything that expands more than `$?`, or an echo that ends the list, must stay as it is.
"""

import sys
import tempfile
import unittest
from pathlib import Path

from aider.native_command_policy import CommandRule, CommandRules, PolicyAction, decide
from aider.native_status_tail import without_status_tail
from aider.native_tool_context import ToolContext
from aider.native_tools_shell import run_command

ROOT = Path("/work/project")
TRUSTED = CommandRules(allow=(CommandRule("python", trust_unsandboxed=True),))


class StatusTailTest(unittest.TestCase):
    def test_exit_status_echo_and_ignored_failure_are_dropped(self) -> None:
        cases = {
            'python -m shop 2>&1; echo "exit: $?"': "python -m shop 2>&1",
            'python todo.py done 99; echo "Exit code: $?"': "python todo.py done 99",
            "python -m app; echo $?": "python -m app",
            "python -m app && echo exit=$?": "python -m app",
            "python -m shop --help 2>&1 || true": "python -m shop --help 2>&1",
            'python -m app || true; echo "EXIT: $?"': "python -m app",
            'python a.py; echo "---"; python b.py; echo "exit: $?"': 'python a.py; echo "---"; python b.py',
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(without_status_tail(command), expected)

    def test_other_tails_are_unchanged(self) -> None:
        cases = [
            "python -m app",
            'python -m app; echo "done"',
            'python -m app; echo "$HOME $?"',
            'python -m app; echo "$(id) $?"',
            "python -m app; echo `id` $?",
            'python -m app; echo "exit: $?" > out.txt',
            "sh -c 'python -m app; echo $?'",
            'echo "exit: $?"',
            "python -m app || truename",
        ]
        for command in cases:
            with self.subTest(command=command):
                self.assertEqual(without_status_tail(command), command)


class SeparatorEchoTest(unittest.TestCase):
    def action(self, command: str) -> PolicyAction:
        return decide(command, ROOT, TRUSTED, False).action

    def test_a_literal_echo_between_two_allowed_commands_is_not_judged(self) -> None:
        self.assertIs(self.action('python -m shop --help; echo "---"; python -m shop x.json'), PolicyAction.ALLOW)
        self.assertIs(self.action('python -c "import a" 2>&1; echo "---"; python -c "import b" 2>&1'),
                      PolicyAction.ALLOW)

    def test_an_echo_that_ends_the_list_expands_or_redirects_is_still_asked(self) -> None:
        for command in (
            'python -m shop; echo "done"',
            'python -m shop; echo "$HOME"; python -m shop',
            "python -m shop; echo x > out; python -m shop",
            "python -m shop; echo x | sh; python -m shop",
            'echo "---"; curl https://x',
        ):
            with self.subTest(command=command):
                self.assertIs(self.action(command), PolicyAction.ASK)


class RealExitCodeTest(unittest.TestCase):
    def test_run_command_reports_the_exit_code_the_echo_would_have_hidden(self) -> None:
        program = Path(sys.executable).name
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules = CommandRules(allow=(CommandRule(program, trust_unsandboxed=True),))
            ctx = ToolContext(
                root=root, list_files=list, find_tags=lambda a, r: [], approve=lambda p, t, d: False,
                on_edit=lambda p: None, dry_run=False,
                check_command=lambda command: decide(command, root, rules, False),
            )
            (root / "fail.py").write_text("raise SystemExit(3)\n")
            result = run_command(ctx, f'{sys.executable} fail.py; echo "exit: $?"')
        self.assertTrue(result.startswith("Exit code: 3"), result)


if __name__ == "__main__":
    unittest.main()
