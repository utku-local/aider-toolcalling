"""Tests for the research tool: a question answered in a separate conversation with read-only tools.
A scripted model plays both conversations; the main agent must receive only the sub-conversation's answer, and
the file the sub-conversation read must not appear in the main conversation's requests.
The sub-conversation must also stop at its round cap, or after repeated refused calls, and answer without tools.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from test_agent_coder import tool_call
from test_coder_native_tools import FINAL_TEXT, MODEL_NAME, ScriptedModel, make_completion

from aider.coders import Coder
from aider.coders.native_subtask import SUBTASK_MAX_REPEAT_REFUSALS, SUBTASK_MAX_ROUNDS, SUBTASK_SYSTEM
from aider.io import InputOutput
from aider.models import Model

ANSWER = "calc.py line 2: add() subtracts instead of adding."
SECRET_LINE = "return a - b  # only the sub-conversation reads this"


class ResearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "calc.py"), "w") as handle:
            handle.write(f"def add(a, b):\n    {SECRET_LINE}\n")
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def coder(self) -> Coder:
        return Coder.create(main_model=Model(MODEL_NAME), edit_format="agent", io=InputOutput(yes=True, pretty=False),
                            fnames=[], use_git=False, map_tokens=0, auto_lint=False, stream=False)

    def test_only_the_answer_reaches_the_main_conversation(self) -> None:
        scripted = ScriptedModel([
            make_completion(tool_calls=tool_call("m1", "research", {"question": "Why does add() fail?"})),
            make_completion(tool_calls=tool_call("s1", "read_file", {"path": "calc.py"})),
            make_completion(ANSWER),
            make_completion(FINAL_TEXT),
        ])
        with patch("aider.models.litellm.completion", side_effect=scripted):
            self.coder().run(with_message="Investigate add().")

        main_first, sub_first, sub_second, main_last = scripted.requests
        self.assertEqual(sub_first["messages"][0]["content"], SUBTASK_SYSTEM)
        self.assertNotIn("research", [t["function"]["name"] for t in sub_first["tools"]])
        self.assertTrue(any(SECRET_LINE in (m.get("content") or "") for m in sub_second["messages"]))
        research_result = [m for m in main_last["messages"] if m.get("tool_call_id") == "m1"][0]
        self.assertEqual(research_result["content"], ANSWER)
        self.assertFalse(any(SECRET_LINE in str(m.get("content")) for m in main_last["messages"]))

    def test_subtask_stops_at_its_round_cap(self) -> None:
        # Distinct calls, so the repeat limit does not end the sub-conversation before the round cap.
        loop = [make_completion(tool_calls=tool_call(f"s{i}", "list_files", {"path": f"dir{i}"}))
                for i in range(SUBTASK_MAX_ROUNDS)]
        scripted = ScriptedModel(
            [make_completion(tool_calls=tool_call("m1", "research", {"question": "List it"}))]
            + loop + [make_completion(ANSWER), make_completion(FINAL_TEXT)]
        )
        with patch("aider.models.litellm.completion", side_effect=scripted):
            self.coder().run(with_message="Explore.")
        self.assertEqual(scripted.requests[SUBTASK_MAX_ROUNDS + 1]["tool_choice"], "none")

    def test_task_answers_after_repeated_refusals(self) -> None:
        # Commands need an explicit yes, so with yes=True the first call is declined and each repeat is refused.
        repeats = SUBTASK_MAX_REPEAT_REFUSALS + 1
        declined = [make_completion(tool_calls=tool_call(f"s{i}", "run_command", {"command": "echo hi"}))
                    for i in range(repeats)]
        scripted = ScriptedModel(
            [make_completion(tool_calls=tool_call("m1", "task", {"brief": "Run echo hi."}))]
            + declined + [make_completion(ANSWER), make_completion(FINAL_TEXT)]
        )
        with patch("aider.models.litellm.completion", side_effect=scripted):
            self.coder().run(with_message="Delegate it.")
        sub_requests = scripted.requests[1:repeats + 2]
        self.assertTrue(all(r.get("tool_choice") != "none" for r in sub_requests[:-1]))
        self.assertEqual(sub_requests[-1]["tool_choice"], "none")


if __name__ == "__main__":
    unittest.main()
