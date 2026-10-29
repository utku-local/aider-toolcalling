"""Tests for what the agent is told about its command environment and when it is told to stop and ask.
They check the system-prompt note for sandboxed and unsandboxed sessions, the hints added to refused connections
and sandbox denials, the localhost rules in the sandbox profile, and the note after several failing commands.
A sandbox test on macOS checks that localhost is reachable while writes outside the project stay blocked.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_coder_native_tools import MODEL_NAME

from aider.coders import Coder
from aider.io import InputOutput
from aider.models import Model
from aider.native_environment import (
    REFUSED_HINT,
    SANDBOX_HINT,
    UNSANDBOXED_NOTE,
    command_hint,
    environment_note,
)
from aider.native_sandbox import sandbox_available, sandbox_profile, sandboxed_argv
from aider.native_tool_calls import ToolCall
from aider.native_tool_ledger import OperationLedger, OperationStatus
from aider.native_tool_loop import (
    FAILING_STREAK_LIMIT,
    REPEAT_REFUSAL_MARKER,
    build_tool_round_messages,
)
from aider.native_toolcalling import NativeToolRegistry

STREAK_MARKER = "commands all failed"


class EnvironmentNoteTest(unittest.TestCase):
    def test_sandboxed_note_names_localhost_and_asking_the_user(self) -> None:
        note = environment_note(True)
        self.assertIn("localhost", note)
        self.assertIn("internet is blocked", note)
        self.assertIn("tell the user", note)

    def test_unsandboxed_note_says_so(self) -> None:
        self.assertIn("without a sandbox", environment_note(False))

    def test_note_is_in_the_main_prompt_once_and_not_in_the_reminder(self) -> None:
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as root:
            os.chdir(root)
            try:
                coder = Coder.create(main_model=Model(MODEL_NAME), edit_format="agent",
                                     io=InputOutput(yes=True, pretty=False), fnames=[], use_git=False, map_tokens=0)
                prompt = coder.fmt_system_prompt(coder.gpt_prompts.main_system)
                reminder = coder.fmt_system_prompt(coder.gpt_prompts.system_reminder)
            finally:
                os.chdir(cwd)
        self.assertEqual(prompt.count(UNSANDBOXED_NOTE), 1)
        self.assertNotIn(UNSANDBOXED_NOTE, reminder)


class CommandHintTest(unittest.TestCase):
    def test_refused_connection_points_at_a_stopped_service(self) -> None:
        self.assertEqual(command_hint("ConnectionRefusedError: [Errno 61] Connection refused", False), REFUSED_HINT)

    def test_sandbox_denial_is_explained_only_when_sandboxed(self) -> None:
        output = "PermissionError: [Errno 1] Operation not permitted"
        self.assertEqual(command_hint(output, True), SANDBOX_HINT)
        self.assertEqual(command_hint(output, False), "")

    def test_ordinary_failure_gets_no_hint(self) -> None:
        self.assertEqual(command_hint("AssertionError: 1 != 2", True), "")


class SandboxProfileTest(unittest.TestCase):
    def test_profile_allows_localhost_only(self) -> None:
        profile = sandbox_profile(Path("/tmp"))
        self.assertIn('(remote ip "localhost:*")', profile)
        self.assertIn("(deny network*)", profile)

    @unittest.skipUnless(sandbox_available(), "sandbox-exec is macOS only")
    def test_localhost_is_reachable_and_outside_writes_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            serve = (
                "python3 -c \"import socket; s=socket.socket(); s.bind(('127.0.0.1', 0)); s.listen(); "
                "c=socket.create_connection(s.getsockname()); print('connected')\""
            )
            reached = subprocess.run(sandboxed_argv(Path(root), serve), capture_output=True, text=True)
            self.assertIn("connected", reached.stdout)
            outside = Path.home() / "agent-sandbox-should-not-exist"
            blocked = subprocess.run(sandboxed_argv(Path(root), f"touch {outside}"), capture_output=True, text=True)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertFalse(outside.exists())


class FailingStreakTest(unittest.TestCase):
    def test_note_after_several_failing_commands_and_reset_on_success(self) -> None:
        outcomes = iter(["Exit code: 1\nboom"] * FAILING_STREAK_LIMIT + ["Exit code: 0\nok", "Exit code: 1\nboom"])
        registry = NativeToolRegistry()
        schema = {"type": "object", "properties": {"n": {"type": "integer"}}}
        registry.register("run_command", "Run", schema, lambda n: next(outcomes))
        ledger = OperationLedger()
        ledger.start_request()

        def run(index: int) -> str:
            call = ToolCall(f"c{index}", "run_command", f'{{"n": {index}}}')
            return build_tool_round_messages(registry, "", [call], ledger)[1]["content"]

        results = [run(i) for i in range(FAILING_STREAK_LIMIT + 2)]
        self.assertTrue(all(STREAK_MARKER not in r for r in results[: FAILING_STREAK_LIMIT - 1]))
        self.assertIn(STREAK_MARKER, results[FAILING_STREAK_LIMIT - 1])
        self.assertNotIn(STREAK_MARKER, results[-1])


class DeclinedRepeatTest(unittest.TestCase):
    def test_a_declined_call_is_not_asked_again(self) -> None:
        asked: list[str] = []
        registry = NativeToolRegistry()

        def declined() -> str:
            asked.append("ask")
            ledger.mark(OperationStatus.DENIED)
            return "The user declined this action."

        registry.register("run_command", "Run", {"type": "object", "properties": {}}, declined)
        ledger = OperationLedger()
        ledger.start_request()
        first = build_tool_round_messages(registry, "", [ToolCall("a", "run_command", "{}")], ledger)
        again = build_tool_round_messages(registry, "", [ToolCall("b", "run_command", "{}")], ledger)
        self.assertEqual(first[1]["content"], "The user declined this action.")
        self.assertTrue(again[1]["content"].startswith(REPEAT_REFUSAL_MARKER))
        self.assertEqual(len(asked), 1)
