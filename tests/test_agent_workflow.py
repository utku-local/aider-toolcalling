"""Tests for the agent workflow tools: command policy, read-only git, task list, snapshots and project config.
The policy cases check that decisions follow parsed argv, not text: compound commands, outside paths and risky
programs are never auto-allowed, and allow rules only auto-approve when trusted or sandboxed.
Git and snapshot tests run against a real temporary repository.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from aider.coders.native_agent_config import AgentConfigError, instruction_files, parse_config
from aider.native_command_policy import CommandRule, CommandRules, PolicyAction, Risk, decide
from aider.native_snapshots import SnapshotStore
from aider.native_todo import TodoError, TodoList, todo_write
from aider.native_tool_context import ToolContext
from aider.native_tools_git import GitToolError, git
from aider.native_tools_shell import POLICY_REFUSAL, run_command

ROOT = Path("/work/project")
TRUSTED = CommandRules(allow=(CommandRule("pytest", trust_unsandboxed=True),))
UNTRUSTED = CommandRules(allow=(CommandRule("pytest"), CommandRule("git", ("status",))))


class CommandPolicyTest(unittest.TestCase):
    def action(self, command: str, rules: CommandRules = TRUSTED, sandboxed: bool = False) -> PolicyAction:
        return decide(command, ROOT, rules, sandboxed).action

    def test_trusted_rule_allows_plain_invocations(self) -> None:
        for command in ("pytest -q tests", "python -m pytest -x", "python3 -m pytest tests/test_a.py"):
            with self.subTest(command=command):
                self.assertIs(self.action(command), PolicyAction.ALLOW)

    def test_untrusted_rules_allow_only_in_a_sandbox(self) -> None:
        self.assertIs(self.action("pytest", UNTRUSTED), PolicyAction.ASK)
        self.assertIs(self.action("pytest", UNTRUSTED, sandboxed=True), PolicyAction.ALLOW)
        self.assertIs(self.action("git status", UNTRUSTED, sandboxed=True), PolicyAction.ALLOW)
        self.assertIs(self.action("git commit -m x", UNTRUSTED, sandboxed=True), PolicyAction.ASK)

    def test_compound_and_outside_paths_are_never_auto_allowed(self) -> None:
        for command in (
            "pytest; rm -rf ~",
            "pytest | tee out",
            "pytest > /tmp/out",
            "pytest $(cat args)",
            "pytest `id`",
            "FOO=1 pytest",
            "pytest ../other",
            "pytest /etc",
            "pytest --rootdir=/",
            "pytest 'unterminated",
        ):
            with self.subTest(command=command):
                self.assertIs(self.action(command, sandboxed=True), PolicyAction.ASK)

    def test_risks_are_classified(self) -> None:
        cases = {
            "curl https://x": Risk.NETWORK,
            "git push origin main": Risk.GIT_REMOTE,
            "pip install requests": Risk.PACKAGE_INSTALL,
            "rm build.log": Risk.DELETE,
            "git clean -fd": Risk.DELETE,
        }
        for command, risk in cases.items():
            with self.subTest(command=command):
                decision = decide(command, ROOT, CommandRules(), False)
                self.assertIs(decision.action, PolicyAction.ASK)
                self.assertIn(risk, decision.risks)

    def test_hard_denials(self) -> None:
        for command in ("sudo make install", "git push --force", "git push -f origin x", "rm -rf .", "rm -r /tmp"):
            with self.subTest(command=command):
                self.assertIs(self.action(command), PolicyAction.DENY)

    def test_deny_rules_win(self) -> None:
        rules = CommandRules(allow=(CommandRule("make", trust_unsandboxed=True),), deny=(CommandRule("make"),))
        self.assertIs(self.action("make", rules), PolicyAction.DENY)


class ShellPolicyIntegrationTest(unittest.TestCase):
    def ctx(self, root: Path, rules: CommandRules, asked: list) -> ToolContext:
        return ToolContext(
            root=root, list_files=list, find_tags=lambda a, r: [],
            approve=lambda p, t, d: asked.append(t) or False, on_edit=lambda p: None, dry_run=False,
            check_command=lambda command: decide(command, root, rules, False),
        )

    def test_allow_skips_approval_and_deny_never_asks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asked: list = []
            ctx = self.ctx(Path(tmp), CommandRules(allow=(CommandRule("echo", trust_unsandboxed=True),)), asked)
            self.assertTrue(run_command(ctx, "echo hi").startswith("Exit code: 0"))
            self.assertTrue(run_command(ctx, "sudo ls").startswith(POLICY_REFUSAL))
            self.assertEqual(asked, [])
            run_command(ctx, "curl https://example.com")
            self.assertIn("network access", asked[0])


class GitToolTest(unittest.TestCase):
    def test_read_only_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            ident = ["-c", "user.email=t@t", "-c", "user.name=t"]
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "a.txt").write_text("one\n")
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            subprocess.run(["git", *ident, "commit", "-qm", "first"], cwd=root, check=True)
            (root / "a.txt").write_text("two\n")
            ctx = ToolContext(root, list, lambda a, r: [], lambda p, t, d: True, lambda p: None, False)

            self.assertIn("+two", git(ctx, "diff"))
            self.assertIn("first", git(ctx, "log", ["--oneline", "-n", "1"]))
            self.assertIn("a.txt", git(ctx, "status", ["--short"]))
            for subcommand, args in (("push", []), ("diff", ["--output=x"]), ("log", ["-c", "x"]),
                                     ("diff", ["--", "../outside"])):
                with self.subTest(subcommand=subcommand, args=args), self.assertRaises(Exception):
                    git(ctx, subcommand, args)
            with self.assertRaises(GitToolError):
                git(ctx, "commit", ["-m", "x"])


class TodoAndSnapshotTest(unittest.TestCase):
    def test_todo_list(self) -> None:
        todos = TodoList()
        rendered = todo_write(todos, [{"content": "Read code", "status": "done"},
                                      {"content": "Fix bug", "status": "in_progress"}, {"content": "Run tests"}])
        self.assertEqual(rendered, "[x] Read code\n[~] Fix bug\n[ ] Run tests")
        self.assertEqual(len(todos.open_items()), 2)
        for bad in ([{"status": "done"}], [{"content": "x", "status": "maybe"}], ["text"]):
            with self.subTest(bad=bad), self.assertRaises(TodoError):
                todos.replace(bad)

    def test_snapshots_restore_newest_request_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            changed, created = Path(tmp, "a.txt"), Path(tmp, "new.txt")
            changed.write_text("original")
            store = SnapshotStore()
            store.capture(1, str(changed))
            changed.write_text("first edit")
            store.capture(2, str(changed))
            store.capture(2, str(created))
            changed.write_text("second edit")
            created.write_text("made")

            self.assertEqual(store.undo_latest(), sorted([str(changed), str(created)]))
            self.assertEqual(changed.read_text(), "first edit")
            self.assertFalse(created.exists())
            store.undo_latest()
            self.assertEqual(changed.read_text(), "original")
            self.assertEqual(store.undo_latest(), [])


class AgentConfigTest(unittest.TestCase):
    def test_parse_config(self) -> None:
        config = parse_config(json.loads(
            '{"commands": {"allow": [{"program": "pytest", "trust_unsandboxed": true}],'
            ' "deny": [{"program": "git", "subcommands": ["push"]}]}}'
        ))
        self.assertEqual(config.rules.allow, (CommandRule("pytest", (), True),))
        self.assertEqual(config.rules.deny, (CommandRule("git", ("push",), False),))
        for bad in ([], {"commands": []}, {"commands": {"allow": [{"name": "x"}]}}):
            with self.subTest(bad=bad), self.assertRaises(AgentConfigError):
                parse_config(bad)

    def test_instruction_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(instruction_files(tmp), [])
            Path(tmp, "AGENTS.md").write_text("Use tabs.")
            self.assertEqual(instruction_files(tmp), [str(Path(tmp, "AGENTS.md"))])


if __name__ == "__main__":
    unittest.main()
