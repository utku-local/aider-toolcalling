"""Tests for two repairs of malformed agent calls: a leading cd into the project root, and garbled tool arguments.
Both inputs come from a Heretic session: `cd /abs/root && cmd` on every command, and todo_write sent as
`{"items\"": "[...]"}`. Each repair must leave anything ambiguous unchanged.
"""

import json
import tempfile
import unittest
from pathlib import Path

from aider.coders.native_agent_config import CommandRules
from aider.native_argument_repair import repair_arguments
from aider.native_command_policy import decide
from aider.native_root_cd import without_root_cd
from aider.native_tool_calls import ToolCall
from aider.native_toolcalling import NativeToolError, NativeToolRegistry

TODO_PARAMETERS = {
    "type": "object",
    "properties": {"items": {"type": "array"}, "note": {"type": "string"}},
    "required": ["items"],
}
ITEMS = [{"content": "Find the provider", "status": "done"}]


class RootCdTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "sub").mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_cd_into_root_is_dropped(self) -> None:
        cases = [
            f"cd {self.root} && pip list | grep curl",
            f"cd '{self.root}' && pip list | grep curl",
            f"cd {self.root}/ ; pip list | grep curl",
            "cd . && pip list | grep curl",
        ]
        for command in cases:
            with self.subTest(command=command):
                self.assertEqual(without_root_cd(command, self.root), "pip list | grep curl")

    def test_other_commands_are_unchanged(self) -> None:
        cases = [
            "cd sub && make",
            "cd /tmp && ls",
            f"cd {self.root}",
            f"cd {self.root} || exit 1",
            f"echo cd {self.root} && ls",
            "pytest -q",
        ]
        for command in cases:
            with self.subTest(command=command):
                self.assertEqual(without_root_cd(command, self.root), command)

    def test_stripped_command_raises_no_risk(self) -> None:
        command = f"cd {self.root} && pip list 2>/dev/null | grep -i curl"
        self.assertTrue(decide(command, self.root, CommandRules(), False).risks)
        self.assertFalse(decide(without_root_cd(command, self.root), self.root, CommandRules(), False).risks)

    def test_symlinked_root_matches(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        link = Path(holder.name) / "link"
        link.symlink_to(self.root)
        self.assertEqual(without_root_cd(f"cd {link} && ls", self.root), "ls")


class ArgumentRepairTest(unittest.TestCase):
    def test_heretic_todo_payload_is_repaired(self) -> None:
        garbled = {'items"': json.dumps(ITEMS)}
        self.assertEqual(repair_arguments(TODO_PARAMETERS, garbled), {"items": ITEMS})

    def test_valid_and_ambiguous_arguments_are_unchanged(self) -> None:
        cases = [
            {"items": ITEMS},
            {"items": "not json"},
            {"items": json.dumps({"a": 1})},
            {"note": json.dumps(ITEMS)},
            {"items": ITEMS, 'items"': ITEMS},
            {"unknown": 1},
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                self.assertEqual(repair_arguments(TODO_PARAMETERS, arguments), arguments)

    def test_registry_runs_the_repaired_call(self) -> None:
        registry = NativeToolRegistry()
        registry.register("todo_write", "Write the plan.", TODO_PARAMETERS, lambda items, note=None: len(items))
        garbled = json.dumps({'items"': json.dumps(ITEMS)})
        self.assertEqual(registry.execute(ToolCall("c1", "todo_write", garbled)).content, "1")
        with self.assertRaises(NativeToolError):
            registry.execute(ToolCall("c2", "todo_write", json.dumps({"itemz": ITEMS})))


if __name__ == "__main__":
    unittest.main()
