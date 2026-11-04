"""Tests for the agent mode system prompt text in aider/coders/agent_prompts.py.
They pin instructions that measured runs showed a model needs, so a later prompt trim cannot drop them silently.
The checks read the prompt string only and need no model, project or network.
"""

import unittest

from aider.coders.agent_prompts import AgentPrompts

REPRODUCE_FIRST = "first reproduce it with a command and read its real output"
EDIT_AFTER = "change code\nonly after you have seen the failure"
TEST_CHEAPEST = "test the cheapest form of it with one command before you write code"
NO_SPREAD = "do not spread a fix across files"
STATUS_NOT_PROOF = "A 200 status is not proof"


class ReproduceFirstTest(unittest.TestCase):
    def test_main_prompt_asks_to_reproduce_a_failure_before_editing(self) -> None:
        self.assertIn(REPRODUCE_FIRST, AgentPrompts.main_system)
        self.assertIn(EDIT_AFTER, AgentPrompts.main_system)

    def test_reproduce_comes_before_the_done_rule(self) -> None:
        prompt = AgentPrompts.main_system
        self.assertLess(prompt.index(REPRODUCE_FIRST), prompt.index("Never call something done"))


class TestBeforeFixTest(unittest.TestCase):
    def test_prompt_asks_to_test_the_cheapest_candidate_before_writing(self) -> None:
        self.assertIn(TEST_CHEAPEST, AgentPrompts.main_system)
        self.assertIn(NO_SPREAD, AgentPrompts.main_system)

    def test_prompt_warns_that_a_200_status_is_not_proof(self) -> None:
        self.assertIn(STATUS_NOT_PROOF, AgentPrompts.main_system)

    def test_test_before_fix_sits_in_the_reproduce_paragraph(self) -> None:
        prompt = AgentPrompts.main_system
        self.assertLess(prompt.index(REPRODUCE_FIRST), prompt.index(TEST_CHEAPEST))
        self.assertLess(prompt.index(TEST_CHEAPEST), prompt.index("Never call something done"))


if __name__ == "__main__":
    unittest.main()
