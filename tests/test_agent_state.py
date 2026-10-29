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
from aider.native_tool_compaction import COMPACTED_PREFIX, add_working_state, compact_tool_history
from aider.native_tool_ledger import OperationLedger, OperationStatus
from aider.native_tool_loop import REPEAT_NOTE, REPEAT_REFUSAL_MARKER, REPLAYED_NOTE, build_tool_round_messages
from aider.native_tool_summary import exit_code, summarize_result
from aider.native_toolcalling import NativeToolRegistry
from aider.native_working_state import STATE_HEADING, render_working_state


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


class RepeatHintTest(unittest.TestCase):
    def test_identical_read_calls_get_a_hint(self) -> None:
        registry = NativeToolRegistry()
        registry.register("read_file", "Read", {"type": "object", "properties": {"path": {"type": "string"}}},
                          lambda path: "content")
        registry.register("run_command", "Run", {"type": "object", "properties": {}}, lambda: "Exit code: 0")
        ledger = OperationLedger()
        ledger.start_request()
        first = build_tool_round_messages(registry, "", [ToolCall("a", "read_file", '{"path": "x"}')], ledger)
        again = build_tool_round_messages(registry, "", [ToolCall("b", "read_file", '{"path": "x"}')], ledger)
        third = build_tool_round_messages(registry, "", [ToolCall("b3", "read_file", '{"path": "x"}')], ledger)
        self.assertTrue(third[1]["content"].startswith(REPEAT_REFUSAL_MARKER))
        self.assertEqual(ledger.repeat_refusals(REPEAT_REFUSAL_MARKER), 1)
        other = build_tool_round_messages(registry, "", [ToolCall("c", "read_file", '{"path": "y"}')], ledger)
        self.assertEqual(first[1]["content"], "content")
        self.assertTrue(again[1]["content"].startswith(REPEAT_NOTE))
        self.assertEqual(other[1]["content"], "content")
        ledger.start_request()
        fresh = build_tool_round_messages(registry, "", [ToolCall("f", "read_file", '{"path": "x"}')], ledger)
        self.assertEqual(fresh[1]["content"], "content")


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


def tool_round(call_id: str, name: str, arguments: dict, content: str) -> list[dict]:
    call = {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
    return [
        {"role": "assistant", "content": "", "tool_calls": [call]},
        {"role": "tool", "tool_call_id": call_id, "name": name, "content": content},
    ]


class CompactionTest(unittest.TestCase):
    def history(self, *rounds: list[dict]) -> list[dict]:
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "go"}]
        for messages_of_round in rounds:
            messages += messages_of_round
        return messages

    def tools(self, messages: list[dict]) -> list[str]:
        return [m["content"] for m in messages if m["role"] == "tool"]

    def test_superseded_reads_are_always_summarized(self) -> None:
        original = self.history(
            tool_round("r1", "read_file", {"path": "a.py"}, "old\n"),
            tool_round("r2", "read_file", {"path": "b.py"}, "b\n"),
            tool_round("r3", "read_file", {"path": "a.py"}, "new\n"),
        )
        self.assertEqual(self.tools(compact_tool_history(original)), ["old\n", "b\n", "new\n"])
        compacted = compact_tool_history(original, trigger_chars=0, target_chars=10**6)
        self.assertEqual(self.tools(compacted), [COMPACTED_PREFIX + "1 lines", "b\n", "new\n"])
        self.assertEqual(self.tools(original), ["old\n", "b\n", "new\n"])

    def test_different_ranges_are_different_reads(self) -> None:
        original = self.history(
            tool_round("r1", "read_file", {"path": "a.py", "start_line": 1, "end_line": 9}, "x\n"),
            tool_round("r2", "read_file", {"path": "a.py", "start_line": 10, "end_line": 20}, "y\n"),
        )
        self.assertEqual(self.tools(compact_tool_history(original, trigger_chars=0)), ["x\n", "y\n"])

    def test_other_results_go_before_reads(self) -> None:
        original = self.history(
            tool_round("r1", "read_file", {"path": "a.py"}, "a\nb\n"),
            tool_round("s1", "search_code", {"pattern": "x"}, "f:1: x\n" * 30),
            tool_round("r2", "read_file", {"path": "b.py"}, "c\n"),
            tool_round("r3", "read_file", {"path": "c.py"}, "d\n"),
        )
        target = len("sysgo") + len("a\nb\n") + len(COMPACTED_PREFIX + "30 results") + len("c\n") + len("d\n")
        compacted = self.tools(compact_tool_history(original, keep_rounds=2, trigger_chars=0, target_chars=target))
        self.assertEqual(compacted, ["a\nb\n", COMPACTED_PREFIX + "30 results", "c\n", "d\n"])
        everything = self.tools(compact_tool_history(original, keep_rounds=2, trigger_chars=0, target_chars=0))
        self.assertEqual(everything[0], COMPACTED_PREFIX + "2 lines")
        self.assertEqual(everything[2:], ["c\n", "d\n"])

    def test_small_histories_are_not_compacted(self) -> None:
        original = self.history(*[tool_round(f"r{i}", "read_file", {"path": f"{i}.py"}, "a\n") for i in range(4)])
        self.assertEqual(compact_tool_history(original), original)

    def test_working_state_is_added_only_when_it_changes(self) -> None:
        messages = self.history(tool_round("r1", "read_file", {"path": "a.py"}, "a\n"))
        before = list(messages)
        add_working_state(messages, STATE_HEADING + "\nA")
        add_working_state(messages, STATE_HEADING + "\nA")
        self.assertEqual(messages[: len(before)], before)
        self.assertEqual(messages[len(before):], [{"role": "user", "content": STATE_HEADING + "\nA"}])
        add_working_state(messages, STATE_HEADING + "\nB")
        add_working_state(messages, "")
        self.assertEqual([m["content"] for m in messages[len(before):]], [STATE_HEADING + "\nA", STATE_HEADING + "\nB"])


class PrefixStabilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "calc.py"), "w") as handle:
            handle.write("def add(a, b):\n    return a - b\n")
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_each_round_extends_the_previous_request(self) -> None:
        coder = Coder.create(
            main_model=Model(MODEL_NAME), edit_format="agent", io=InputOutput(yes=True, pretty=False),
            fnames=[], use_git=False, map_tokens=0, auto_lint=False, stream=False,
        )
        read = tool_call("r1", "read_file", {"path": "calc.py"})
        fix = tool_call("e1", "edit_file", {"path": "calc.py", "old_string": "a - b", "new_string": "a + b"})
        scripted = ScriptedModel([make_completion(tool_calls=read), make_completion(tool_calls=fix),
                                  make_completion(FINAL_TEXT)])
        with patch("aider.models.litellm.completion", side_effect=scripted):
            coder.run(with_message="Fix add().")

        requests = [r["messages"] for r in scripted.requests]
        for earlier, later in zip(requests, requests[1:]):
            self.assertEqual(later[: len(earlier)], earlier)


class RepeatLoopTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "calc.py"), "w") as handle:
            handle.write("x = 1\n")
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_identical_reads_are_refused_and_the_loop_ends(self) -> None:
        coder = Coder.create(
            main_model=Model(MODEL_NAME), edit_format="agent", io=InputOutput(yes=True, pretty=False),
            fnames=[], use_git=False, map_tokens=0, auto_lint=False, stream=False,
        )
        same_read = [make_completion(tool_calls=tool_call(f"r{i}", "read_file", {"path": "calc.py"}))
                     for i in range(5)]
        scripted = ScriptedModel(same_read + [make_completion(FINAL_TEXT)])
        with patch("aider.models.litellm.completion", side_effect=scripted):
            coder.run(with_message="Look at calc.py.")

        statuses = [r.status for r in coder.native_ledger.records]
        self.assertEqual(statuses.count(OperationStatus.EXECUTED), 2)
        self.assertEqual(coder.native_ledger.repeat_refusals(REPEAT_REFUSAL_MARKER), 3)
        self.assertEqual(scripted.requests[-1]["tool_choice"], "none")
        self.assertEqual(coder.partial_response_content, FINAL_TEXT)


    def test_a_file_change_resets_the_repeat_count(self) -> None:
        ledger = OperationLedger()
        ledger.start_request()
        test = {"command": "python -m unittest"}
        record(ledger, "run_command", test, "exit 1", OperationStatus.EXECUTED)
        record(ledger, "run_command", test, "exit 1", OperationStatus.EXECUTED)
        self.assertEqual(ledger.times_run("run_command", json.dumps(test)), 2)
        record(ledger, "multi_edit", {"path": "calc.py"}, "ok", OperationStatus.EXECUTED)
        self.assertEqual(ledger.times_run("run_command", json.dumps(test)), 0)

    def test_identical_commands_are_refused_until_a_file_changes(self) -> None:
        registry = NativeToolRegistry()
        registry.register("run_command", "Run", {"type": "object", "properties": {}}, lambda: "Exit code: 0")
        registry.register("edit_file", "Edit", {"type": "object", "properties": {}}, lambda: "Edited")
        ledger = OperationLedger()
        ledger.start_request()

        def run(call_id: str, tool: str) -> str:
            return build_tool_round_messages(registry, "", [ToolCall(call_id, tool, "{}")], ledger)[1]["content"]

        self.assertEqual([run(f"c{i}", "run_command") for i in range(2)], ["Exit code: 0"] * 2)
        self.assertTrue(run("c2", "run_command").startswith(REPEAT_REFUSAL_MARKER))
        run("e", "edit_file")
        self.assertEqual(run("c3", "run_command"), "Exit code: 0")

    def test_an_identical_edit_is_applied_only_once(self) -> None:
        registry = NativeToolRegistry()
        registry.register("edit_file", "Edit", {"type": "object", "properties": {}}, lambda: "Edited")
        ledger = OperationLedger()
        ledger.start_request()

        def edit(call_id: str) -> str:
            return build_tool_round_messages(registry, "", [ToolCall(call_id, "edit_file", "{}")], ledger)[1]["content"]

        self.assertEqual(edit("e1"), "Edited")
        self.assertTrue(edit("e2").startswith(REPEAT_REFUSAL_MARKER))
        self.assertEqual(ledger.repeat_refusals(REPEAT_REFUSAL_MARKER), 1)
        ledger.start_request()
        self.assertEqual(edit("e3"), "Edited")

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
        # The last completion answers the one-time reminder to verify the unverified change.
        scripted = ScriptedModel([make_completion(tool_calls=tool_call("e1", "edit_file", fix)), outage,
                                  make_completion(FINAL_TEXT), make_completion(FINAL_TEXT)])
        scripted_call = scripted.__call__

        def respond(**kwargs: object) -> object:
            result = scripted_call(**kwargs)
            if isinstance(result, Exception):
                raise result
            return result

        with patch("aider.models.litellm.completion", side_effect=respond):
            coder.run(with_message="Fix add().")

        self.assertEqual(len(coder.native_ledger.records), 1)
        retry = scripted.requests[-2]
        retry_tools = [m for m in retry["messages"] if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in retry_tools], ["e1"])
        with open("calc.py") as handle:
            self.assertIn("return a + b", handle.read())
        self.assertIn("Files changed: calc.py", retry["messages"][-1]["content"])


if __name__ == "__main__":
    unittest.main()
