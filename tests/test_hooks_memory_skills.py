"""Tests for tool hooks, the remember tool and skills.
They check that a failing before hook blocks the call through the loop and an after hook's output becomes a note,
that hooks need the user's yes and never run unattended, that notes accumulate in the memory file, and that
project skills override user skills and are listed with their first line.
Hook commands are stubbed and files live in a temporary folder, so nothing runs in a shell.
"""

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from aider.coders.native_agent_config import AgentConfigError, parse_config
from aider.coders.native_hook_setup import project_hooks
from aider.native_hooks import HookRule, ToolHooks
from aider.native_loop_options import LoopOptions
from aider.native_memory_skills import (
    MEMORY_FILE,
    SKILLS_DIR,
    MemorySkillError,
    find_skills,
    remember,
    skills_listing,
    use_skill,
)
from aider.native_tool_calls import ToolCall
from aider.native_tool_ledger import OperationLedger
from aider.native_tool_loop import build_tool_round_messages
from aider.native_toolcalling import NativeToolRegistry


def run_with(hooks: ToolHooks, tool: str) -> str:
    registry = NativeToolRegistry()
    registry.register(tool, "Tool", {"type": "object", "properties": {}}, lambda: "done")
    ledger = OperationLedger()
    ledger.start_request()
    call = ToolCall("a", tool, "{}")
    return build_tool_round_messages(registry, "", [call], ledger, LoopOptions(hooks=hooks))[1]["content"]


class HookTest(unittest.TestCase):
    def test_failing_before_hook_blocks_and_after_hook_notes(self) -> None:
        def run(command: str, env: dict) -> tuple[int, str]:
            return (1, "edits are frozen") if command == "check" else (0, f"saw {env['AIDER_TOOL']}")

        hooks = ToolHooks((HookRule("edit_file|write_file", "check"),), (HookRule(".*", "log"),), run)
        self.assertIn("blocked by a project hook (check): edits are frozen", run_with(hooks, "edit_file"))
        self.assertEqual(run_with(hooks, "read_file"), "done\n[hook log] saw read_file")

    def test_hooks_need_a_yes_and_never_run_unattended(self) -> None:
        config = parse_config({"hooks": {"before_tool": [{"tools": "edit_file", "command": "true"}]}})
        answers = []

        def coder(answer: bool) -> SimpleNamespace:
            def confirm(title: str, subject: str = None, explicit_yes_required: bool = False) -> bool:
                answers.append(explicit_yes_required)
                return answer

            return SimpleNamespace(native_agent_config=config, root=".", io=SimpleNamespace(confirm_ask=confirm))

        self.assertIsNone(project_hooks(coder(False), lambda c: ["sh", "-c", c]))
        self.assertIsNotNone(project_hooks(coder(True), lambda c: ["sh", "-c", c]))
        self.assertEqual(answers, [True, True])
        self.assertIsNone(project_hooks(SimpleNamespace(native_agent_config=parse_config({})), lambda c: []))

    def test_bad_hook_config_is_refused(self) -> None:
        with self.assertRaises(AgentConfigError):
            parse_config({"hooks": {"before_tool": [{"tools": "(", "command": "x"}]}})
        with self.assertRaises(AgentConfigError):
            parse_config({"hooks": {"after_tool": [{"tools": "x"}]}})


class MemorySkillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "project"
        self.home = Path(self.tmp.name) / "home"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_notes_accumulate(self) -> None:
        remember(self.root, "Run tests with  python -m pytest", date(2026, 10, 29))
        remember(self.root, "The API key lives in .env", date(2026, 10, 30))
        text = (self.root / MEMORY_FILE).read_text()
        self.assertIn("- 2026-10-29: Run tests with python -m pytest\n- 2026-10-30:", text)
        with self.assertRaises(MemorySkillError):
            remember(self.root, "   ", date(2026, 10, 30))

    def test_project_skill_wins_and_is_listed(self) -> None:
        for base, text in ((self.home, "# User release\nold steps"), (self.root, "# Cut a release\n1. bump")):
            (base / SKILLS_DIR).mkdir(parents=True)
            (base / SKILLS_DIR / "release.md").write_text(text)
        (self.home / SKILLS_DIR / "review.md").write_text("Review a diff\nsteps")
        skills = find_skills(self.root, self.home)
        self.assertEqual(sorted(skills), ["release", "review"])
        self.assertIn("- release: Cut a release", skills_listing(skills))
        self.assertIn("1. bump", use_skill(skills, "release"))
        self.assertEqual(skills_listing({}), "")
        with self.assertRaises(MemorySkillError):
            use_skill(skills, "deploy")
