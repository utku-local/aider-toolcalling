"""Tests for the evaluation set's pure parts: metric parsing, aggregation and the task checks themselves.
Every task's check must fail on the untouched project, otherwise a task would pass without the agent doing anything.
The checks run in a temporary copy of each task's files with the current interpreter.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evals.metrics import RunMetrics, TaskResult, parse_metrics, summarize
from evals.tasks import TASKS

SAMPLE_OUTPUT = """Running tool: read_file {"path": "a.py"}
  -> 3 lines
Running tool: edit_file {"path": "a.py"}
  -> Error: old_string was not found
Native tools: 2 round(s), 2 call(s), 12.5s
Tokens: 3.4k sent, 120 received.
Native tools: 1 round(s), 3 call(s), 4.0s
Tokens: 6.8k sent, 247 received.
"""


class MetricsTest(unittest.TestCase):
    def test_parse_metrics(self) -> None:
        metrics = parse_metrics(SAMPLE_OUTPUT)
        self.assertEqual((metrics.rounds, metrics.calls, metrics.tool_seconds), (3, 5, 16.5))
        self.assertEqual((metrics.tokens_sent, metrics.tokens_received), (6800, 247))
        self.assertEqual(metrics.tool_errors, 1)

    def test_missing_values_stay_none(self) -> None:
        metrics = parse_metrics("nothing here")
        self.assertIsNone(metrics.rounds)
        self.assertIsNone(metrics.tokens_sent)

    def test_summarize(self) -> None:
        empty = RunMetrics(None, None, None, None, None, 0)
        results = [
            TaskResult("a", True, 10.0, RunMetrics(2, 3, 5.0, 1000, 10, 1)),
            TaskResult("b", False, 20.0, empty),
        ]
        summary = summarize(results)
        self.assertEqual((summary["passed"], summary["success_rate"]), (1, 0.5))
        self.assertEqual((summary["mean_seconds"], summary["mean_rounds"]), (15.0, 2))


class TaskChecksTest(unittest.TestCase):
    def test_every_check_fails_before_the_agent_runs(self) -> None:
        self.assertEqual(len({t.name for t in TASKS}), len(TASKS))
        for task in TASKS:
            with self.subTest(task=task.name), tempfile.TemporaryDirectory() as tmp:
                for rel, text in task.files.items():
                    (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
                    (Path(tmp) / rel).write_text(text)
                done = subprocess.run([sys.executable, "-c", task.check], cwd=tmp, capture_output=True)
                self.assertNotEqual(done.returncode, 0)


if __name__ == "__main__":
    unittest.main()
