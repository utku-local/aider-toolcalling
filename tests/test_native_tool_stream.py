"""Tests for streamed native tool calls: the delta accumulator and a streaming Coder end to end.
The fake stream splits ids, names and JSON arguments across chunks the way OpenAI-compatible servers do.
The end-to-end test checks that a streamed tool call runs and that the follow-up reply is streamed as well.
"""

import os
import tempfile
import unittest
from types import SimpleNamespace
from typing import Any, Iterator, Optional
from unittest.mock import patch

from test_coder_native_tools import FINAL_TEXT, MODEL_NAME, ScriptedModel

from aider.coders import Coder
from aider.io import InputOutput
from aider.models import Model
from aider.native_tool_calls import ToolCall, normalize_tool_calls
from aider.native_tool_stream import ToolCallAccumulator


def delta_call(index: int, call_id: Optional[str], name: Optional[str], args: str) -> SimpleNamespace:
    function = SimpleNamespace(name=name, arguments=args)
    return SimpleNamespace(index=index, id=call_id, function=function)


def chunk(content: Optional[str] = None, tool_calls: Any = None) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=None)])


def stream(*chunks: SimpleNamespace) -> Iterator[SimpleNamespace]:
    return iter(chunks)


class ToolCallAccumulatorTest(unittest.TestCase):
    def test_fragments_are_assembled_per_index(self) -> None:
        acc = ToolCallAccumulator()
        self.assertFalse(acc.add(SimpleNamespace(content="Hi", tool_calls=None)))
        self.assertTrue(acc.add(SimpleNamespace(tool_calls=[delta_call(0, "a", "read_file", '{"pa')])))
        acc.add(SimpleNamespace(tool_calls=[delta_call(1, "b", "list_files", "{}")]))
        acc.add(SimpleNamespace(tool_calls=[delta_call(0, None, None, 'th": "x.py"}')]))

        calls = normalize_tool_calls(acc.message("Hi"), 0)
        self.assertEqual(
            calls,
            [ToolCall("a", "read_file", '{"path": "x.py"}'), ToolCall("b", "list_files", "{}")],
        )

    def test_dict_deltas_and_missing_index(self) -> None:
        acc = ToolCallAccumulator()
        acc.add({"tool_calls": [{"id": "c", "function": {"name": "f", "arguments": {"k": 1}}}]})
        self.assertEqual(normalize_tool_calls(acc.message(""), 0), [ToolCall("c", "f", '{"k": 1}')])

    def test_text_only_stream_has_no_calls(self) -> None:
        self.assertEqual(normalize_tool_calls(ToolCallAccumulator().message("plain"), 0), [])


class StreamingCoderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "hello.txt"), "w") as handle:
            handle.write("hello\n")
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_streamed_tool_call_round_trip(self) -> None:
        coder = Coder.create(
            main_model=Model(MODEL_NAME),
            edit_format="ask",
            io=InputOutput(yes=True, pretty=False),
            fnames=[],
            use_git=False,
            map_tokens=0,
            stream=True,
            native_tools=True,
        )
        scripted = ScriptedModel(
            [
                stream(
                    chunk("Let me check. "),
                    chunk(tool_calls=[delta_call(0, "s1", "read_file", '{"path": ')]),
                    chunk(tool_calls=[delta_call(0, None, None, '"hello.txt"}')]),
                ),
                stream(chunk(FINAL_TEXT[:10]), chunk(FINAL_TEXT[10:])),
            ]
        )
        with patch("aider.models.litellm.completion", side_effect=scripted):
            coder.run(with_message="Read hello.txt.")

        self.assertEqual(len(scripted.requests), 2)
        self.assertTrue(all(request["stream"] for request in scripted.requests))
        assistant, tool = scripted.requests[1]["messages"][-2:]
        self.assertEqual(assistant["content"], "Let me check.")
        self.assertEqual(assistant["tool_calls"][0]["function"]["arguments"], '{"path": "hello.txt"}')
        self.assertEqual((tool["tool_call_id"], tool["content"]), ("s1", "hello\n"))
        self.assertEqual(coder.partial_response_content, FINAL_TEXT)


if __name__ == "__main__":
    unittest.main()
