"""Tests for the agent mode system prompt text in aider/coders/agent_prompts.py.
They pin instructions that measured runs showed a model needs, so a later prompt trim cannot drop them silently.
The checks read the prompt string only and need no model, project or network.
"""

import unittest

from aider.coders.agent_prompts import AgentPrompts

REPRODUCE_FIRST = "first reproduce it with a command and read its real output"
EDIT_AFTER = "change code\nonly after you have seen the failure"


class ReproduceFirstTest(unittest.TestCase):
    def test_main_prompt_asks_to_reproduce_a_failure_before_editing(self) -> None:
        self.assertIn(REPRODUCE_FIRST, AgentPrompts.main_system)
        self.assertIn(EDIT_AFTER, AgentPrompts.main_system)

    def test_reproduce_comes_before_the_done_rule(self) -> None:
        prompt = AgentPrompts.main_system
        self.assertLess(prompt.index(REPRODUCE_FIRST), prompt.index("Never call something done"))


if __name__ == "__main__":
    unittest.main()
