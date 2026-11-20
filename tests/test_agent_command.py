"""Tests for the /agent command and for the note that tells the model which mode commands exist.
The command is checked through the SwitchCoder it raises, so no model or terminal is needed.
The note must reach both the ask and the agent prompt and survive prompt formatting.
"""

import unittest

from aider.coders.agent_prompts import AgentPrompts
from aider.coders.ask_prompts import AskPrompts
from aider.commands import Commands, SwitchCoder
from aider.native_session_help import AGENT_MODE, SESSION_COMMANDS_NOTE


class AgentCommandTest(unittest.TestCase):
    def test_agent_without_a_request_switches_to_agent_mode(self) -> None:
        commands = Commands(None, None)
        with self.assertRaises(SwitchCoder) as raised:
            commands.cmd_agent("  ")
        self.assertEqual(raised.exception.kwargs, {"edit_format": AGENT_MODE, "summarize_from_coder": False})

    def test_agent_is_listed_as_a_command(self) -> None:
        self.assertIn("/agent", Commands(None, None).get_commands())


class SessionNoteTest(unittest.TestCase):
    def test_both_prompts_name_the_mode_commands(self) -> None:
        for prompt in (AskPrompts.main_system, AgentPrompts.main_system):
            for command in ("/agent", "/ask", "/chat-mode", "/help"):
                self.assertIn(command, prompt)

    def test_the_note_has_no_format_fields(self) -> None:
        self.assertEqual(SESSION_COMMANDS_NOTE.format(), SESSION_COMMANDS_NOTE)
        self.assertIn("English", AskPrompts.main_system.format(language="English"))


if __name__ == "__main__":
    unittest.main()
