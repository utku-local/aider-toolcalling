"""Tests for the task sub-agent and for background exit notices.
A scripted model plays both conversations: the sub-agent edits a file with the real tools and the main agent gets
only its report; the sub-agent has every tool except ask_user and task, and its edit is applied to the project.
A background process that exits on its own is reported once in the next request, and a stopped one never is.
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_agent_coder import tool_call
from test_coder_native_tools import FINAL_TEXT, MODEL_NAME, ScriptedModel, make_completion

from aider.coders import Coder
from aider.coders.native_subtask import TASK_SYSTEM
from aider.io import InputOutput
from aider.models import Model
from aider.native_tools_background import ProcessManager

REPORT = "Changed calc.py: add() now adds. Verified by reading it back."
WAIT_STEP_SECONDS = 0.05
WAIT_STEPS = 100


class TaskTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "calc.py"), "w") as handle:
            handle.write("def add(a, b):\n    return a - b\n")
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_sub_agent_edits_and_only_its_report_returns(self) -> None:
        coder = Coder.create(main_model=Model(MODEL_NAME), edit_format="agent", io=InputOutput(yes=True, pretty=False),
                             fnames=[], use_git=False, map_tokens=0, auto_lint=False, stream=False)
        fix = {"path": "calc.py", "old_string": "a - b", "new_string": "a + b"}
        scripted = ScriptedModel([
            make_completion(tool_calls=tool_call("m1", "task", {"brief": "Make add() add."})),
            make_completion(tool_calls=tool_call("s1", "read_file", {"path": "calc.py"})),
            make_completion(tool_calls=tool_call("s2", "edit_file", fix)),
            make_completion(REPORT),
            make_completion(FINAL_TEXT),
            make_completion(FINAL_TEXT),
        ])
        with patch("aider.models.litellm.completion", side_effect=scripted):
            coder.run(with_message="Fix add() via a sub-agent.")

        sub_first = scripted.requests[1]
        self.assertEqual(sub_first["messages"][0]["content"], TASK_SYSTEM)
        names = {t["function"]["name"] for t in sub_first["tools"]}
        self.assertIn("edit_file", names)
        self.assertFalse({"ask_user", "task"} & names)
        self.assertIn("return a + b", Path("calc.py").read_text())
        main_after = scripted.requests[4]["messages"]
        self.assertEqual([m["content"] for m in main_after if m.get("tool_call_id") == "m1"], [REPORT])


class BackgroundNoticeTest(unittest.TestCase):
    def test_exit_is_reported_once_and_stops_are_not(self) -> None:
        manager = ProcessManager()
        quick = manager.start([sys.executable, "-c", "raise SystemExit(3)"], Path.cwd(), "quick")
        slow = manager.start([sys.executable, "-c", "import time; time.sleep(30)"], Path.cwd(), "slow")
        for _ in range(WAIT_STEPS):
            if manager.get(quick).process.poll() is not None:
                break
            time.sleep(WAIT_STEP_SECONDS)
        manager.stop(slow)
        notices = manager.exit_notices()
        self.assertEqual(len(notices), 1)
        self.assertIn(f"{quick} (quick) exited with code 3", notices[0])
        self.assertEqual(manager.exit_notices(), [])
        manager.stop_all()
