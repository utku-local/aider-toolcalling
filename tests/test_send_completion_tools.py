"""Unit tests for the native tool parameters of Model.send_completion.
They patch litellm.completion so no provider or network is involved, and inspect the kwargs it receives.
They also assert that the development copy of aider is the one under test, not the installed release.
"""

import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import patch

import aider.models
from aider.models import Model

REPO_ROOT = Path(__file__).resolve().parents[1]
MESSAGES = [{"role": "user", "content": "test"}]
LEGACY_FUNCTION = {"name": "edit_file", "parameters": {"type": "object"}}
NATIVE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Test tool {name}",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    for name in ("tool_one", "tool_two")
]


def make_model() -> Model:
    """Build a Model without running __init__, so no provider lookup happens."""
    model = object.__new__(Model)
    model.name = "openai/test-model"
    model.use_temperature = False
    model.extra_params = None
    model.verbose = False
    model.is_deepseek_r1 = lambda: False
    model.is_ollama = lambda: False
    return model


class SendCompletionToolsTest(unittest.TestCase):
    def call(
        self,
        functions: Optional[list] = None,
        tools: Optional[list] = None,
        tool_choice: Optional[Any] = None,
    ) -> dict:
        response = SimpleNamespace(choices=[])
        with patch("aider.models.litellm.completion", return_value=response) as mocked:
            _, result = make_model().send_completion(
                messages=MESSAGES,
                functions=functions,
                stream=False,
                temperature=0,
                tools=tools,
                tool_choice=tool_choice,
            )
        self.assertIs(result, response)
        return mocked.call_args.kwargs

    def test_dev_copy_is_under_test(self) -> None:
        self.assertEqual(Path(aider.models.__file__).resolve().parents[1], REPO_ROOT)

    def test_legacy_functions_force_first_function(self) -> None:
        kwargs = self.call(functions=[LEGACY_FUNCTION])
        self.assertEqual(kwargs["tools"], [{"type": "function", "function": LEGACY_FUNCTION}])
        self.assertEqual(
            kwargs["tool_choice"],
            {"type": "function", "function": {"name": "edit_file"}},
        )

    def test_native_tools_pass_through_with_auto_choice(self) -> None:
        kwargs = self.call(tools=NATIVE_TOOLS)
        self.assertEqual(kwargs["tools"], NATIVE_TOOLS)
        self.assertEqual(kwargs["tool_choice"], "auto")

    def test_explicit_tool_choice_is_preserved(self) -> None:
        choice = {"type": "function", "function": {"name": "tool_two"}}
        kwargs = self.call(tools=NATIVE_TOOLS, tool_choice=choice)
        self.assertEqual(kwargs["tool_choice"], choice)

    def test_no_tools_sends_no_tool_kwargs(self) -> None:
        kwargs = self.call()
        self.assertNotIn("tools", kwargs)
        self.assertNotIn("tool_choice", kwargs)


if __name__ == "__main__":
    unittest.main()
