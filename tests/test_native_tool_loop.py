"""Unit tests for the pure helpers in aider.native_tool_loop and the registry they drive.
They feed normalized ToolCalls through a small registry and inspect the assistant and tool messages produced.
Error paths (unknown tool, bad JSON, schema violations, raising handler) must become tool results, not exceptions.
"""

import json
import unittest

from aider.native_tool_calls import ToolCall
from aider.native_tool_loop import TOOL_ERROR_PREFIX, build_tool_round_messages
from aider.native_toolcalling import NativeToolRegistry

ECHO_PARAMETERS = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "times": {"type": "integer"}},
    "required": ["text"],
}


def boom() -> str:
    raise RuntimeError("handler failed")


def echo(text: str, times: int = 1) -> str:
    return text.upper() * times


def make_registry() -> NativeToolRegistry:
    registry = NativeToolRegistry()
    registry.register("echo", "Echo text", ECHO_PARAMETERS, echo)
    registry.register("boom", "Always fails", {"type": "object", "properties": {}}, boom)
    return registry


def call(call_id: str, name: str, arguments: object) -> ToolCall:
    text = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return ToolCall(id=call_id, name=name, arguments=text)


class NativeToolLoopTest(unittest.TestCase):
    def run_round(self, *calls: ToolCall) -> list[dict]:
        return build_tool_round_messages(make_registry(), "thinking", list(calls))

    def test_successful_round_builds_assistant_and_tool_messages(self) -> None:
        out = self.run_round(call("c1", "echo", {"text": "hi"}), call("c2", "echo", {"text": "yo"}))

        self.assertEqual(out[0]["role"], "assistant")
        self.assertEqual(out[0]["content"], "thinking")
        self.assertEqual([c["id"] for c in out[0]["tool_calls"]], ["c1", "c2"])
        self.assertEqual(out[0]["tool_calls"][0]["function"]["arguments"], '{"text": "hi"}')
        self.assertEqual(
            out[1:],
            [
                {"role": "tool", "tool_call_id": "c1", "name": "echo", "content": "HI"},
                {"role": "tool", "tool_call_id": "c2", "name": "echo", "content": "YO"},
            ],
        )

    def assert_error(self, tool_call: ToolCall, *fragments: str) -> None:
        result = self.run_round(tool_call)[1]
        self.assertEqual(result["tool_call_id"], tool_call.id)
        self.assertTrue(result["content"].startswith(TOOL_ERROR_PREFIX), result["content"])
        for fragment in fragments:
            self.assertIn(fragment, result["content"])

    def test_unknown_tool_lists_available_tools(self) -> None:
        self.assert_error(call("c1", "missing", {}), "not registered", "boom", "echo")

    def test_bad_json_is_reported(self) -> None:
        self.assert_error(call("c1", "echo", "{not json"), "Invalid JSON")

    def test_non_object_arguments_are_reported(self) -> None:
        self.assert_error(call("c1", "echo", "[1, 2]"), "JSON object")

    def test_schema_violations_are_reported(self) -> None:
        self.assert_error(call("c1", "echo", {}), "missing required argument 'text'")
        self.assert_error(call("c2", "echo", {"text": "a", "loud": True}), "unknown argument 'loud'")
        self.assert_error(call("c3", "echo", {"text": 5}), "'text' must be of type string")
        self.assert_error(call("c4", "echo", {"text": "a", "times": True}), "type integer")

    def test_handler_exception_is_reported(self) -> None:
        self.assert_error(call("c1", "boom", {}), "handler failed")

    def test_optional_arguments_reach_the_handler(self) -> None:
        out = self.run_round(call("c1", "echo", {"text": "ab", "times": 2}))
        self.assertEqual(out[1]["content"], "ABAB")


if __name__ == "__main__":
    unittest.main()
