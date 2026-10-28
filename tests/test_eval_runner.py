"""Tests for how the eval runner starts the agent: flags, seed and the interpreter on PATH for real tasks.
subprocess.run is replaced so no agent or model runs; the test inspects the command and environment it receives.
Each run must pass its own seed so repeated runs sample independently.
"""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from evals.real_tasks import RealTask
from evals.run_evals import run_agent
from evals.tasks import TASKS


class RunAgentTest(unittest.TestCase):
    def call(self, task: object, seed: int) -> tuple[list, dict]:
        done = SimpleNamespace(stdout="out", stderr="")
        with patch("evals.run_evals.subprocess.run", return_value=done) as run:
            output, _ = run_agent(task, Path("/tmp"), "", 10, seed)
        self.assertEqual(output, "out")
        return run.call_args.args[0], run.call_args.kwargs["env"]

    def test_seed_and_flags(self) -> None:
        command, _ = self.call(TASKS[0], 1002)
        self.assertIn("--agent", command)
        self.assertEqual(command[command.index("--seed") + 1], "1002")

    def test_real_task_puts_its_interpreter_first_on_path(self) -> None:
        task = RealTask("t", "/repo", "abc", "fix: x", ("a.py",), ("tests/test_a.py",), ("a.py",),
                        "/venvs/proj/bin/python", "unittest")
        command, env = self.call(task, 1001)
        self.assertTrue(env["PATH"].startswith("/venvs/proj/bin"))
        self.assertIn("tests/test_a.py", command[-1])


if __name__ == "__main__":
    unittest.main()
