"""Unit tests for aider.native_tool_calls and aider.native_tool_schema.
They cover the response shapes servers send: objects or dicts, string or dict arguments, missing ids and
Qwen-style <tool_call> blocks in the text, plus the JSON schema checks applied to decoded arguments.
Both modules are pure, so the tests build fake messages and never touch the network.
"""

import unittest
from types import SimpleNamespace

from aider.native_tool_calls import (
    EMPTY_ARGUMENTS,
    UNKNOWN_TOOL_NAME,
    ToolCall,
    normalize_tool_calls,
    visible_content,
)
from aider.native_tool_calls import ToolCall as Call
from aider.native_tool_schema import coerce_integers, validate_arguments, wire_parameters
from aider.native_toolcalling import NativeToolRegistry


def obj_call(call_id: object, name: str, arguments: object) -> SimpleNamespace:
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


class NormalizeToolCallsTest(unittest.TestCase):
    def test_object_calls_with_string_arguments(self) -> None:
        message = SimpleNamespace(content=None, tool_calls=[obj_call("a", "read_file", '{"path": "x"}')])
        self.assertEqual(
            normalize_tool_calls(message, 0), [ToolCall("a", "read_file", '{"path": "x"}')]
        )

    def test_dict_calls_with_dict_arguments(self) -> None:
        message = {
            "content": "",
            "tool_calls": [{"id": "b", "function": {"name": "list_files", "arguments": {"path": "."}}}],
        }
        self.assertEqual(
            normalize_tool_calls(message, 0), [ToolCall("b", "list_files", '{"path": "."}')]
        )

    def test_missing_ids_get_synthetic_ones(self) -> None:
        message = SimpleNamespace(
            content=None, tool_calls=[obj_call(None, "a", "{}"), obj_call("", "b", None)]
        )
        calls = normalize_tool_calls(message, 3)
        self.assertEqual([c.id for c in calls], ["call_3_0", "call_3_1"])
        self.assertEqual(calls[1].arguments, EMPTY_ARGUMENTS)

    def test_missing_function_name_is_unknown(self) -> None:
        message = {"tool_calls": [{"id": "x"}]}
        self.assertEqual(normalize_tool_calls(message, 0)[0].name, UNKNOWN_TOOL_NAME)

    def test_text_tool_calls_are_parsed_and_stripped(self) -> None:
        content = (
            "Let me look.\n"
            '<tool_call>\n{"name": "read_file", "arguments": {"path": "a.py"}}\n</tool_call>\n'
            "<tool_call>not json</tool_call>"
        )
        message = SimpleNamespace(content=content, tool_calls=None)
        self.assertEqual(
            normalize_tool_calls(message, 1), [ToolCall("call_1_0", "read_file", '{"path": "a.py"}')]
        )
        self.assertEqual(visible_content(message), "Let me look.")

    def test_structured_calls_win_over_text(self) -> None:
        message = SimpleNamespace(
            content='<tool_call>{"name": "x", "arguments": {}}</tool_call>',
            tool_calls=[obj_call("s", "y", "{}")],
        )
        self.assertEqual([c.name for c in normalize_tool_calls(message, 0)], ["y"])

    def test_no_calls(self) -> None:
        self.assertEqual(normalize_tool_calls(None, 0), [])
        self.assertEqual(normalize_tool_calls(SimpleNamespace(content="hi"), 0), [])


class ValidateArgumentsTest(unittest.TestCase):
    SCHEMA = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["path"],
    }

    def test_valid_arguments(self) -> None:
        self.assertEqual(validate_arguments(self.SCHEMA, {"path": "a", "limit": 3}), [])

    def test_problems_are_listed(self) -> None:
        problems = validate_arguments(self.SCHEMA, {"limit": 1.5, "extra": 1})
        self.assertEqual(len(problems), 3)

    def test_booleans_are_not_integers(self) -> None:
        self.assertTrue(validate_arguments(self.SCHEMA, {"path": "a", "limit": True}))

    def test_schema_without_properties_rejects_arguments(self) -> None:
        self.assertTrue(validate_arguments({"type": "object"}, {"x": 1}))
        self.assertEqual(validate_arguments({"type": "object"}, {}), [])


if __name__ == "__main__":
    unittest.main()


LINES = {"type": "object", "properties": {"start_line": {"type": "integer", "description": "First line."}}}


class IntegerWireTest(unittest.TestCase):
    def test_integers_are_sent_as_whole_numbers_without_changing_the_registered_schema(self) -> None:
        wire = wire_parameters(LINES)
        self.assertEqual(wire["properties"]["start_line"]["type"], "number")
        self.assertIn("whole number", wire["properties"]["start_line"]["description"])
        self.assertEqual(LINES["properties"]["start_line"]["type"], "integer")

    def test_whole_number_floats_become_ints(self) -> None:
        self.assertEqual(coerce_integers(LINES, {"start_line": 120.0}), {"start_line": 120})
        self.assertEqual(coerce_integers(LINES, {"start_line": 1.5}), {"start_line": 1.5})
        self.assertTrue(validate_arguments(LINES, coerce_integers(LINES, {"start_line": 1.5})))

    def test_registry_runs_a_call_with_a_float_line_number(self) -> None:
        registry = NativeToolRegistry()
        registry.register("read_file", "Read", LINES, lambda start_line: f"{start_line!r}")
        self.assertEqual(registry.schemas()[0]["function"]["parameters"]["properties"]["start_line"]["type"], "number")
        self.assertEqual(registry.execute(Call("a", "read_file", '{"start_line": 120.0}')).content, "120")
