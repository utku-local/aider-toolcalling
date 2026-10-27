"""End-to-end tests of the native tool loop through a real Coder with litellm.completion mocked.
A scripted model first requests list_files and then answers in text, so the test can inspect every request.
It also covers the legacy path without --native-tools, the round limit, and the --native-tools CLI flag.
"""

import copy
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from aider.args import get_parser
from aider.coders import Coder
from aider.io import InputOutput
from aider.models import Model
from aider.coders.native_tool_rounds import MAX_CONTINUATIONS

ROUND_BUDGET = 2

MODEL_NAME = "openai/test-model"
FINAL_TEXT = "The project has one file."


def make_completion(content: Any = None, tool_calls: Any = None) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )


def list_files_call(call_id: str) -> list[SimpleNamespace]:
    function = SimpleNamespace(name="list_files", arguments=json.dumps({"path": "."}))
    return [SimpleNamespace(id=call_id, type="function", function=function)]


class ScriptedModel:
    """Returns the scripted completions in order and snapshots each request."""

    def __init__(self, completions: list[SimpleNamespace]) -> None:
        self.completions = list(completions)
        self.requests: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> SimpleNamespace:
        self.requests.append(copy.deepcopy(kwargs))
        return self.completions.pop(0)


class CoderNativeToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "hello.txt"), "w") as handle:
            handle.write("hello\n")
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def make_coder(self, native_tools: bool) -> Coder:
        return Coder.create(
            main_model=Model(MODEL_NAME),
            edit_format="ask",
            io=InputOutput(yes=True, pretty=False),
            fnames=[],
            use_git=False,
            stream=False,
            map_tokens=0,
            native_tools=native_tools,
        )

    def run_coder(self, coder: Coder, scripted: ScriptedModel) -> None:
        with patch("aider.models.litellm.completion", side_effect=scripted):
            coder.run(with_message="What files are there?")

    def test_tool_call_round_trip(self) -> None:
        coder = self.make_coder(native_tools=True)
        scripted = ScriptedModel(
            [make_completion(tool_calls=list_files_call("c1")), make_completion(FINAL_TEXT)]
        )
        self.run_coder(coder, scripted)

        self.assertEqual(len(scripted.requests), 2)
        first, second = scripted.requests
        tool_names = [tool["function"]["name"] for tool in first["tools"]]
        self.assertEqual(
            tool_names, ["read_file", "list_files", "find_files", "search_code", "find_symbol", "git"]
        )
        self.assertEqual(first["tool_choice"], "auto")

        assistant, tool = second["messages"][-2:]
        self.assertEqual(assistant["role"], "assistant")
        self.assertEqual(assistant["tool_calls"][0]["id"], "c1")
        self.assertEqual(tool["role"], "tool")
        self.assertEqual(tool["tool_call_id"], "c1")
        self.assertIn("hello.txt", tool["content"])

        self.assertEqual(coder.partial_response_content, FINAL_TEXT)
        self.assertFalse(coder.partial_response_function_call)
        self.assertEqual(coder.cur_messages[-1], {"role": "assistant", "content": FINAL_TEXT})

    def test_without_native_tools_no_tools_are_sent(self) -> None:
        coder = self.make_coder(native_tools=False)
        scripted = ScriptedModel([make_completion(FINAL_TEXT)])
        self.run_coder(coder, scripted)

        self.assertEqual(len(scripted.requests), 1)
        self.assertNotIn("tools", scripted.requests[0])
        self.assertNotIn("tool_choice", scripted.requests[0])

    def run_until_limit(self, answer: bool, rounds_expected: int) -> tuple[Coder, ScriptedModel]:
        coder = self.make_coder(native_tools=True)
        coder.io = InputOutput(yes=answer, pretty=False)
        coder.max_tool_rounds = ROUND_BUDGET
        completions = [make_completion(tool_calls=list_files_call(f"c{i}")) for i in range(rounds_expected)]
        completions.append(make_completion(FINAL_TEXT, tool_calls=list_files_call("ignored")))
        scripted = ScriptedModel(completions)
        self.run_coder(coder, scripted)
        return coder, scripted

    def test_declined_continuation_forces_a_final_answer(self) -> None:
        coder, scripted = self.run_until_limit(False, ROUND_BUDGET)

        self.assertEqual(len(scripted.requests), ROUND_BUDGET + 1)
        self.assertEqual(scripted.requests[-1]["tool_choice"], "none")
        tool_ids = [m["tool_call_id"] for m in scripted.requests[-1]["messages"] if m["role"] == "tool"]
        self.assertEqual(tool_ids, [f"c{i}" for i in range(ROUND_BUDGET)])
        self.assertFalse(coder.partial_response_function_call)
        self.assertEqual(coder.partial_response_content, FINAL_TEXT)

    def test_approved_continuations_are_capped(self) -> None:
        total = ROUND_BUDGET * (1 + MAX_CONTINUATIONS)
        coder, scripted = self.run_until_limit(True, total)

        self.assertEqual(len(scripted.requests), total + 1)
        self.assertEqual(scripted.requests[-1]["tool_choice"], "none")
        self.assertEqual(coder.partial_response_content, FINAL_TEXT)

    def test_text_tool_calls_and_missing_ids(self) -> None:
        coder = self.make_coder(native_tools=True)
        text_call = '<tool_call>{"name": "read_file", "arguments": {"path": "hello.txt"}}</tool_call>'
        scripted = ScriptedModel([make_completion(text_call), make_completion(FINAL_TEXT)])
        self.run_coder(coder, scripted)

        assistant, tool = scripted.requests[1]["messages"][-2:]
        self.assertEqual(assistant["content"], "")
        self.assertEqual(assistant["tool_calls"][0]["id"], tool["tool_call_id"])
        self.assertEqual(tool["content"], "hello\n")
        self.assertEqual(coder.partial_response_content, FINAL_TEXT)


class NativeToolsFlagTest(unittest.TestCase):
    def parse(self, *argv: str) -> Any:
        return get_parser([], None).parse_args(list(argv))

    def test_flag_defaults_to_false(self) -> None:
        self.assertFalse(self.parse().native_tools)

    def test_flag_enables_native_tools(self) -> None:
        self.assertTrue(self.parse("--native-tools").native_tools)
        self.assertFalse(self.parse("--no-native-tools").native_tools)


if __name__ == "__main__":
    unittest.main()
