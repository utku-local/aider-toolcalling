"""Unit tests for the pure helpers in aider.native_tool_loop.
They feed fake completion messages with tool_calls through a small registry and inspect the produced messages.
Error paths (unknown tool, bad JSON, raising handler) must become tool result messages instead of exceptions.
"""

import json
import unittest
from types import SimpleNamespace
from typing import Any

from aider.native_tool_loop import (
    TOOL_ERROR_PREFIX,
    UNKNOWN_TOOL_NAME,
    build_tool_round_messages,
    get_tool_calls,
    tool_call_name,
)
from aider.native_toolcalling import NativeToolRegistry

ECHO_PARAMETERS = {"type": "object", "properties": {"text": {"type": "string"}}}


def make_call(call_id: str, name: str, arguments: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id, type="function", function=SimpleNamespace(name=name, arguments=arguments)
    )


def make_message(*calls: SimpleNamespace, content: Any = None) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=list(calls) or None)


def boom() -> str:
    raise RuntimeError("handler failed")


def make_registry() -> NativeToolRegistry:
    registry = NativeToolRegistry()
    registry.register("echo", "Echo text", ECHO_PARAMETERS, lambda text: text.upper())
    registry.register("boom", "Always fails", {"type": "object"}, boom)
    return registry


class NativeToolLoopTest(unittest.TestCase):
    def test_get_tool_calls_handles_missing_values(self) -> None:
        self.assertEqual(get_tool_calls(None), [])
        self.assertEqual(get_tool_calls(SimpleNamespace(content="x")), [])
        self.assertEqual(get_tool_calls(make_message()), [])

    def test_tool_call_name_falls_back_to_unknown(self) -> None:
        self.assertEqual(tool_call_name(SimpleNamespace(id="1")), UNKNOWN_TOOL_NAME)

    def test_successful_round_builds_assistant_and_tool_messages(self) -> None:
        message = make_message(
            make_call("c1", "echo", json.dumps({"text": "hi"})),
            make_call("c2", "echo", json.dumps({"text": "yo"})),
        )
        out = build_tool_round_messages(make_registry(), message)

        self.assertEqual(out[0]["role"], "assistant")
        self.assertEqual(out[0]["content"], "")
        self.assertEqual([c["id"] for c in out[0]["tool_calls"]], ["c1", "c2"])
        self.assertEqual(out[0]["tool_calls"][0]["function"]["name"], "echo")
        self.assertEqual(
            out[1:],
            [
                {"role": "tool", "tool_call_id": "c1", "name": "echo", "content": "HI"},
                {"role": "tool", "tool_call_id": "c2", "name": "echo", "content": "YO"},
            ],
        )

    def test_errors_become_tool_results(self) -> None:
        message = make_message(
            make_call("c1", "missing", "{}"),
            make_call("c2", "echo", "{not json"),
            make_call("c3", "boom", "{}"),
        )
        out = build_tool_round_messages(make_registry(), message)

        tool_messages = out[1:]
        self.assertEqual([m["tool_call_id"] for m in tool_messages], ["c1", "c2", "c3"])
        for msg in tool_messages:
            self.assertEqual(msg["role"], "tool")
            self.assertTrue(msg["content"].startswith(TOOL_ERROR_PREFIX), msg["content"])
        self.assertIn("handler failed", tool_messages[2]["content"])


if __name__ == "__main__":
    unittest.main()
