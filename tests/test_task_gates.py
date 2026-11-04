"""Tests for the plan-first and verify-before-finishing checks of the agent loop.
They cover when a change needs a plan (only after exploring, only once per request), when an answer counts as
verified (a passing command after the last change), and the end-to-end flow where an unverified answer is sent
back once and the model runs a check before finishing.
Records are built directly in an operation ledger, so these checks need no model and no real commands.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from test_agent_coder import tool_call
from test_coder_native_tools import FINAL_TEXT, MODEL_NAME, ScriptedModel, make_completion

from aider.coders import Coder
from aider.io import InputOutput
from aider.models import Model
from aider.native_task_gates import (
    PLAN_AFTER_CALLS,
    PLAN_FIRST_MARKER,
    VERIFY_HEADING,
    announces_action,
    completion_nudge,
    needs_plan,
)
from aider.coders.native_tool_rounds import finish_nudge
from aider.native_tool_calls import ToolCall
from aider.native_tool_ledger import OperationLedger, OperationStatus
from aider.native_loop_options import LoopOptions
from aider.native_tool_loop import STREAM_REPETITION_NUDGE, build_tool_round_messages
from aider.native_toolcalling import NativeToolRegistry


def record(ledger: OperationLedger, tool: str, result: str) -> None:
    entry = ledger.begin(f"id{len(ledger.records)}", tool, json.dumps({"n": len(ledger.records)}))
    ledger.finish(entry, result, failed=False)


def explored_ledger(calls: int) -> OperationLedger:
    ledger = OperationLedger()
    ledger.start_request()
    for _ in range(calls):
        record(ledger, "read_file", "content")
    return ledger


class PlanGateTest(unittest.TestCase):
    def test_a_direct_fix_needs_no_plan(self) -> None:
        self.assertFalse(needs_plan(explored_ledger(PLAN_AFTER_CALLS - 1), "edit_file", has_plan=False))

    def test_a_change_after_exploring_needs_a_plan(self) -> None:
        ledger = explored_ledger(PLAN_AFTER_CALLS)
        self.assertTrue(needs_plan(ledger, "edit_file", has_plan=False))
        self.assertFalse(needs_plan(ledger, "edit_file", has_plan=True))
        self.assertFalse(needs_plan(ledger, "read_file", has_plan=False))

    def test_no_plan_is_asked_after_the_first_change(self) -> None:
        ledger = explored_ledger(1)
        record(ledger, "edit_file", "Edited")
        record(ledger, "run_command", "Exit code: 1")
        self.assertFalse(needs_plan(ledger, "write_file", has_plan=False))

    def test_plan_first_is_asked_once_per_request(self) -> None:
        registry = NativeToolRegistry()
        registry.register("edit_file", "Edit", {"type": "object", "properties": {}}, lambda: "Edited")
        ledger = explored_ledger(PLAN_AFTER_CALLS)

        def edit(call_id: str) -> str:
            call = ToolCall(call_id, "edit_file", "{}")
            options = LoopOptions(has_plan=lambda: False)
            return build_tool_round_messages(registry, "", [call], ledger, options)[1]["content"]

        self.assertTrue(edit("e1").startswith(PLAN_FIRST_MARKER))
        self.assertEqual(edit("e2"), "Edited")


class CompletionNudgeTest(unittest.TestCase):
    def test_no_changes_needs_no_check(self) -> None:
        self.assertEqual(completion_nudge(explored_ledger(2), ""), "")

    def test_change_without_a_passing_command_is_sent_back(self) -> None:
        ledger = explored_ledger(1)
        record(ledger, "edit_file", "Edited")
        record(ledger, "run_command", "Exit code: 1\nFAILED")
        self.assertIn("no command has passed", completion_nudge(ledger, ""))

    def test_passing_command_after_the_last_change_is_enough(self) -> None:
        ledger = explored_ledger(1)
        record(ledger, "edit_file", "Edited")
        record(ledger, "run_command", "Exit code: 0\nOK")
        self.assertEqual(completion_nudge(ledger, ""), "")
        record(ledger, "edit_file", "Edited again")
        self.assertNotEqual(completion_nudge(ledger, ""), "")

    def test_open_tasks_are_named(self) -> None:
        ledger = explored_ledger(1)
        record(ledger, "edit_file", "Edited")
        record(ledger, "run_command", "Exit code: 0\nOK")
        self.assertIn("[ ] write docs", completion_nudge(ledger, "[ ] write docs"))

    def test_denied_change_is_not_a_change(self) -> None:
        ledger = explored_ledger(1)
        entry = ledger.begin("d", "edit_file", "{}")
        ledger.mark(OperationStatus.DENIED)
        ledger.finish(entry, "declined", failed=False)
        self.assertEqual(completion_nudge(ledger, ""), "")


class AnnouncesActionTest(unittest.TestCase):
    """A no-tool-call reply that only promises work must be caught so the turn is not treated as finished."""

    def test_narrated_next_step_is_a_promise(self) -> None:
        self.assertTrue(announces_action("Now let me verify my changes and move on to items 4, 5, 6:"))

    def test_the_stuck_in_a_loop_reply_is_a_promise(self) -> None:
        self.assertTrue(announces_action("Sorry, I got stuck in a loop. I'll work on it now."))

    def test_a_report_is_not_a_promise(self) -> None:
        self.assertFalse(announces_action("Items 5 and 6 are done; item 7 is left for you to do."))

    def test_let_me_know_is_not_a_promise(self) -> None:
        self.assertFalse(announces_action("All changes are applied. Let me know if you want anything else."))

    def test_a_trailing_question_is_a_hand_back(self) -> None:
        self.assertFalse(announces_action("I can take two approaches here. Let me run the slow one?"))

    def test_only_the_last_line_decides(self) -> None:
        self.assertTrue(announces_action("Here is what I found.\n\nI'll fix it now."))
        self.assertFalse(announces_action("Let me explain what happened.\nThe tests all pass now."))

    def test_empty_text_is_not_a_promise(self) -> None:
        self.assertFalse(announces_action("   \n  "))


class _TrippedCoder:
    """Minimal stand-in for a coder: only what finish_nudge's repetition branch reads."""

    def __init__(self, tripped: bool) -> None:
        self.native_ledger = OperationLedger()
        self.native_repetition_tripped = tripped


class RepetitionNudgeTest(unittest.TestCase):
    def test_a_tripped_stream_guard_sends_the_reply_back(self) -> None:
        coder = _TrippedCoder(tripped=True)
        self.assertEqual(finish_nudge(coder, None), STREAM_REPETITION_NUDGE)
        # The flag is one-shot: it clears so the next reply is judged on its own.
        self.assertFalse(coder.native_repetition_tripped)


class SendBackFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "calc.py"), "w") as handle:
            handle.write("def add(a, b):\n    return a - b\n")
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_unverified_answer_is_sent_back_once(self) -> None:
        coder = Coder.create(
            main_model=Model(MODEL_NAME), edit_format="agent", io=InputOutput(yes=True, pretty=False),
            fnames=[], use_git=False, map_tokens=0, auto_lint=False, stream=False,
        )
        fix = {"path": "calc.py", "old_string": "a - b", "new_string": "a + b"}
        scripted = ScriptedModel([
            make_completion(tool_calls=tool_call("r0", "read_file", {"path": "calc.py"})),
            make_completion(tool_calls=tool_call("e1", "edit_file", fix)),
            make_completion("Fixed it."),
            make_completion(FINAL_TEXT),
        ])
        with patch("aider.models.litellm.completion", side_effect=scripted):
            coder.run(with_message="Fix add().")

        nudges = [m for m in scripted.requests[-1]["messages"] if VERIFY_HEADING in str(m.get("content"))]
        self.assertEqual(len(nudges), 1)
        self.assertEqual(len(scripted.requests), 4)
        self.assertEqual(coder.partial_response_content, FINAL_TEXT)
