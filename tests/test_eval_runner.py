"""Tests for how the eval runner starts the agent and resumes a run: flags, seed, PATH and skipped tasks.
subprocess.run is replaced so no agent or model runs; the test inspects the command and environment it receives.
Each run must pass its own seed so repeated runs sample independently.
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from evals.real_tasks import RealTask
from evals.metrics import RunMetrics, TaskResult, finished_runs
from evals.run_evals import main, run_agent, settle_after_timeout
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


class ResumeTest(unittest.TestCase):
    def test_resume_skips_finished_tasks_and_appends_the_rest(self) -> None:
        first, second = TASKS[0].name, TASKS[1].name
        metrics = RunMetrics(2, 3, 1.0, 100, 10, 0)
        ran: list[str] = []

        def fake_run(task: object, *rest: object) -> TaskResult:
            ran.append(task.name)
            return TaskResult(task.name, True, 5.0, metrics)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.jsonl"
            path.write_text(json.dumps({**TaskResult(first, False, 9.0, metrics).as_dict(), "run": 1}) + "\n")
            argv = ["run_evals", "--tasks", f"{first},{second}", "--resume", str(path)]
            with patch("sys.argv", argv), patch("evals.run_evals.run_task", fake_run), redirect_stdout(io.StringIO()):
                main()
            done = finished_runs(path.read_text().splitlines())
        self.assertEqual(ran, [second])
        self.assertEqual(sorted(done), sorted([(first, 1), (second, 1)]))
        self.assertFalse(done[(first, 1)].passed)
        self.assertTrue(done[(second, 1)].passed)


class SettleAfterTimeoutTest(unittest.TestCase):
    def test_command_runs_only_after_a_task_that_used_its_whole_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            marker = Path(tmp) / "ran"
            command = f"touch {marker}"
            self.assertFalse(settle_after_timeout(120.0, 2400, command))
            self.assertFalse(marker.exists())
            self.assertFalse(settle_after_timeout(2400.0, 2400, ""))
            self.assertTrue(settle_after_timeout(2400.0, 2400, command))
            self.assertTrue(marker.exists())
            self.assertTrue(settle_after_timeout(2400.0, 2400, "exit 3"))


if __name__ == "__main__":
    unittest.main()
