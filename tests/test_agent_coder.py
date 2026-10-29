"""End-to-end tests of the agent chat mode through a real AgentCoder with litellm.completion mocked.
A scripted model edits a file and tries a shell command, so the tests can check approvals, Aider's post-edit flow,
and that tool exchanges stay in the chat history for later turns.
They also cover the cleanup of orphaned tool messages that keeps the history valid for strict servers.
"""

import json
import os
import subprocess
import tempfile
import unittest
from typing import Any
from unittest.mock import patch

from test_coder_native_tools import FINAL_TEXT, MODEL_NAME, ScriptedModel, make_completion
from types import SimpleNamespace

from aider.coders import AgentCoder, Coder
from aider.io import InputOutput
from aider.models import Model
from aider.native_tool_loop import drop_orphan_tool_messages
from aider.native_tool_context import DENIED_ACTION


def tool_call(call_id: str, name: str, arguments: dict[str, Any]) -> list[SimpleNamespace]:
    function = SimpleNamespace(name=name, arguments=json.dumps(arguments))
    return [SimpleNamespace(id=call_id, type="function", function=function)]


class AgentCoderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "calc.py"), "w") as handle:
            handle.write("def add(a, b):\n    return a - b\n")
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def make_coder(self, stream: bool = False) -> Coder:
        return Coder.create(
            main_model=Model(MODEL_NAME),
            edit_format="agent",
            io=InputOutput(yes=True, pretty=False),
            fnames=[],
            use_git=False,
            map_tokens=0,
            auto_lint=False,
            stream=stream,
        )

    def test_agent_mode_has_the_full_tool_set_and_keeps_streaming(self) -> None:
        coder = self.make_coder(stream=True)
        self.assertIsInstance(coder, AgentCoder)
        self.assertTrue(coder.stream)
        names = {schema["function"]["name"] for schema in coder.native_tools.schemas()}
        self.assertTrue({"edit_file", "write_file", "run_command", "search_code"} <= names)

    def test_edit_is_applied_and_command_needs_explicit_approval(self) -> None:
        coder = self.make_coder()
        fix = {"path": "calc.py", "old_string": "a - b", "new_string": "a + b"}
        scripted = ScriptedModel(
            [
                make_completion(tool_calls=tool_call("r0", "read_file", {"path": "calc.py"})),
                make_completion(tool_calls=tool_call("e1", "edit_file", fix)),
                make_completion(tool_calls=tool_call("r1", "run_command", {"command": "touch ran"})),
                make_completion(FINAL_TEXT),
                # The change was never verified, so the answer is sent back once.
                make_completion(FINAL_TEXT),
            ]
        )
        with patch("aider.models.litellm.completion", side_effect=scripted):
            coder.run(with_message="Fix add().")

        with open("calc.py") as handle:
            self.assertIn("return a + b", handle.read())
        self.assertFalse(os.path.exists("ran"))
        self.assertIn("calc.py", coder.aider_edited_files)
        history = coder.done_messages + coder.cur_messages
        tool_results = {m["tool_call_id"]: m["content"] for m in history if m["role"] == "tool"}
        self.assertIn("1 replacement", tool_results["e1"])
        self.assertEqual(tool_results["r1"], DENIED_ACTION)

    def test_tool_exchanges_are_remembered_by_later_turns(self) -> None:
        coder = self.make_coder()
        read = tool_call("c1", "read_file", {"path": "calc.py"})
        scripted = ScriptedModel(
            [make_completion(tool_calls=read), make_completion(FINAL_TEXT), make_completion("Done.")]
        )
        with patch("aider.models.litellm.completion", side_effect=scripted):
            coder.run(with_message="Read calc.py.")
            coder.run(with_message="What did it contain?")

        history = scripted.requests[-1]["messages"]
        tool_messages = [m for m in history if m["role"] == "tool"]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn("return a - b", tool_messages[0]["content"])


    def test_repo_map_is_capped_in_agent_mode(self) -> None:
        subprocess.run(["git", "init", "-q"], check=True)
        io = InputOutput(yes=True, pretty=False)
        coder = Coder.create(main_model=Model(MODEL_NAME), edit_format="agent", io=io, fnames=[],
                             map_tokens=4096, map_mul_no_files=8, auto_lint=False)
        self.assertEqual((coder.repo_map.max_map_tokens, coder.repo_map.map_mul_no_files), (1024, 1))
        disabled = Coder.create(main_model=Model(MODEL_NAME), edit_format="agent", io=io, fnames=[],
                                map_tokens=0, auto_lint=False)
        self.assertIsNone(disabled.repo_map)

    def test_instruction_files_are_read_only_context(self) -> None:
        with open("AGENTS.md", "w") as handle:
            handle.write("Always use type hints.")
        coder = self.make_coder()
        self.assertIn(os.path.realpath("AGENTS.md"), {os.path.realpath(p) for p in coder.abs_read_only_fnames})

    def test_undo_agent_restores_tool_edits(self) -> None:
        coder = self.make_coder()
        fix = {"path": "calc.py", "old_string": "a - b", "new_string": "a + b"}
        create = {"path": "notes.txt", "content": "todo"}
        scripted = ScriptedModel(
            [
                make_completion(tool_calls=tool_call("e1", "edit_file", fix) + tool_call("w1", "write_file", create)),
                make_completion(FINAL_TEXT),
            ]
        )
        with patch("aider.models.litellm.completion", side_effect=scripted):
            coder.run(with_message="Fix add() and take notes.")
        self.assertTrue(os.path.exists("notes.txt"))

        coder.commands.cmd_undo_agent("")
        with open("calc.py") as handle:
            self.assertIn("return a - b", handle.read())
        self.assertFalse(os.path.exists("notes.txt"))


class DropOrphanToolMessagesTest(unittest.TestCase):
    def test_valid_history_is_unchanged(self) -> None:
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "a"}]},
            {"role": "tool", "tool_call_id": "a", "content": "x"},
            {"role": "assistant", "content": "done"},
        ]
        self.assertEqual(drop_orphan_tool_messages(history), history)

    def test_orphans_and_unanswered_calls_are_removed(self) -> None:
        history = [
            {"role": "tool", "tool_call_id": "old", "content": "x"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "a"}, {"id": "b"}]},
            {"role": "tool", "tool_call_id": "a", "content": "x"},
            {"role": "user", "content": "next"},
            {"role": "tool", "tool_call_id": "a", "content": "late"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "z"}]},
        ]
        cleaned = drop_orphan_tool_messages(history)
        self.assertEqual([m["role"] for m in cleaned], ["user", "assistant", "tool", "user", "assistant"])
        self.assertEqual(cleaned[1]["tool_calls"], [{"id": "a"}])
        self.assertNotIn("tool_calls", cleaned[-1])


if __name__ == "__main__":
    unittest.main()
