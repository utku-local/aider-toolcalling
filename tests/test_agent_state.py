"""Tests for the operation ledger, result summaries, working state and history compaction.
They check that status follows real execution (denied stays denied, replayed ids do not rerun), that the working
state is built from the ledger only, and that compaction never changes the stored history.
An end-to-end test shows an API retry resuming after the tool rounds already executed instead of redoing them.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import litellm
from test_agent_coder import tool_call
from test_coder_native_tools import FINAL_TEXT, MODEL_NAME, ScriptedModel, make_completion

from aider.coders import Coder
from aider.io import InputOutput
from aider.models import Model
from aider.native_tool_calls import ToolCall
from aider.native_tool_compaction import COMPACTED_PREFIX, compact_tool_history, with_working_state
from aider.native_tool_ledger import OperationLedger, OperationStatus
from aider.native_tool_loop import REPLAYED_NOTE, build_tool_round_messages
from aider.native_tool_summary import exit_code, summarize_result
from aider.native_toolcalling import NativeToolRegistry
from aider.native_working_state import render_working_state


def record(ledger: OperationLedger, tool: str, args: dict, result: str, status: OperationStatus) -> None:
    entry = ledger.begin(f"id{len(ledger.records)}", tool, json.dumps(args))
    if status is OperationStatus.DENIED:
        ledger.mark(OperationStatus.DENIED)
    ledger.finish(entry, result, status is OperationStatus.FAILED)


class LedgerTest(unittest.TestCase):
    def test_status_transitions(self) -> None:
        ledger = OperationLedger()
        entry = ledger.begin("a", "edit_file", "{}")
        ledger.mark(OperationStatus.AWAITING_APPROVAL)
        self.assertEqual(entry.status, OperationStatus.AWAITING_APPROVAL)
        ledger.mark(OperationStatus.DENIED)
        ledger.finish(entry, "declined", failed=False)
        self.assertEqual(entry.status, OperationStatus.DENIED)
        self.assertIsNone(ledger.current)

    def test_replayed_call_id_runs_once_per_request(self) -> None:
        runs = []
        registry = NativeToolRegistry()
        registry.register("bump", "Count", {"type": "object", "properties": {}}, lambda: runs.append(1) or "ok")
        ledger = OperationLedger()
        ledger.start_request()
        call = ToolCall("same", "bump", "{}")
        build_tool_round_messages(registry, "", [call], ledger)
        replay = build_tool_round_messages(registry, "", [call], ledger)
        self.assertEqual(len(runs), 1)
        self.assertTrue(replay[1]["content"].startswith(REPLAYED_NOTE))
        ledger.start_request()
        build_tool_round_messages(registry, "", [call], ledger)
        self.assertEqual(len(runs), 2)


class SummaryAndStateTest(unittest.TestCase):
    def test_summaries(self) -> None:
        self.assertEqual(summarize_result("read_file", "a\nb\nc\n"), "3 lines")
        self.assertEqual(summarize_result("search_code", "x:1: a\ny:2: b"), "2 results")
        self.assertEqual(summarize_result("run_command", "Exit code: 1\nok\nFAILED t"), "exit 1: FAILED t")
        self.assertEqual(summarize_result("edit_file", "Error: old_string was not found\nmore"),
                         "Error: old_string was not found")
        self.assertEqual(exit_code("no code here"), None)

    def test_working_state_uses_only_finished_operations(self) -> None:
        ledger = OperationLedger()
        record(ledger, "read_file", {"path": "a.py"}, "x", OperationStatus.EXECUTED)
        record(ledger, "edit_file", {"path": "a.py"}, "Edited", OperationStatus.EXECUTED)
        record(ledger, "edit_file", {"path": "b.py"}, "declined", OperationStatus.DENIED)
        record(ledger, "run_command", {"command": "pytest"}, "Exit code: 2\nboom", OperationStatus.EXECUTED)
        record(ledger, "read_file", {"path": "c.py"}, "Error: Not a file", OperationStatus.FAILED)
        ledger.begin("open", "write_file", json.dumps({"path": "pending.py"}))

        state = render_working_state(ledger.records)
        self.assertIn("Files changed: a.py", state)
        self.assertNotIn("b.py", state.split("Declined")[0])
        self.assertNotIn("pending.py", state)
        self.assertIn("`pytest` -> exit 2", state)
        self.assertIn("Declined by the user: 1", state)
        self.assertIn("read_file: Error: Not a file", state)
        self.assertEqual(render_working_state([]), "")


class CompactionTest(unittest.TestCase):
    def history(self, rounds: int) -> list[dict]:
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "go"}]
        for i in range(rounds):
            messages.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}"}]})
            messages.append({"role": "tool", "tool_call_id": f"c{i}", "name": "read_file", "content": "a\nb\n"})
        return messages

    def test_old_rounds_are_summarized_recent_kept(self) -> None:
        original = self.history(4)
        compacted = compact_tool_history(original, keep_rounds=2)
        tools = [m["content"] for m in compacted if m["role"] == "tool"]
        self.assertEqual(tools[:2], [COMPACTED_PREFIX + "2 lines"] * 2)
        self.assertEqual(tools[2:], ["a\nb\n"] * 2)
        self.assertEqual(original, self.history(4))

    def test_working_state_joins_the_system_message(self) -> None:
        messages = self.history(0)
        self.assertEqual(with_working_state(messages, "STATE")[0]["content"], "sys\n\nSTATE")
        self.assertEqual(with_working_state(messages[1:], "STATE")[0], {"role": "system", "content": "STATE"})
        self.assertEqual(messages[0]["content"], "sys")


class RetryResumeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "calc.py"), "w") as handle:
            handle.write("def add(a, b):\n    return a - b\n")
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_retry_resumes_after_executed_rounds(self) -> None:
        coder = Coder.create(
            main_model=Model(MODEL_NAME), edit_format="agent", io=InputOutput(yes=True, pretty=False),
            fnames=[], use_git=False, map_tokens=0, auto_lint=False, stream=False,
        )
        fix = {"path": "calc.py", "old_string": "a - b", "new_string": "a + b"}
        outage = litellm.APIConnectionError(message="down", llm_provider="openai", model=MODEL_NAME)
        scripted = ScriptedModel([make_completion(tool_calls=tool_call("e1", "edit_file", fix)), outage,
                                  make_completion(FINAL_TEXT)])
        scripted_call = scripted.__call__

        def respond(**kwargs: object) -> object:
            result = scripted_call(**kwargs)
            if isinstance(result, Exception):
                raise result
            return result

        with patch("aider.models.litellm.completion", side_effect=respond):
            coder.run(with_message="Fix add().")

        self.assertEqual(len(coder.native_ledger.records), 1)
        retry_tools = [m for m in scripted.requests[-1]["messages"] if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in retry_tools], ["e1"])
        with open("calc.py") as handle:
            self.assertIn("return a + b", handle.read())
        self.assertIn("Files changed: calc.py", scripted.requests[-1]["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
