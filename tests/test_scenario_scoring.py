"""Tests for the pure scenario scoring and the scenario definitions.
They check token parsing, the four order steps (only executed test commands count), the classification of what
follows a failed call, and the service outcome, which accepts telling the user or starting the server.
The scenario projects are checked to start in the broken state their prompts describe.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evals.scenario_scoring import error_handling, order_score, service_outcome, token_counts
from evals.scenarios import RETEST, SERVICE_START_HINT


def call(tool: str, args: str = "{}", result: str = "", status: str = "executed") -> dict:
    return {"tool": tool, "args": args, "result": result, "status": status}


class TokenTest(unittest.TestCase):
    def test_sums_every_token_line(self) -> None:
        log = "Tokens: 21k sent, 295 received.\nother\nTokens: 1.5k sent, 1k received."
        self.assertEqual(token_counts(log), (22500, 1295))


class OrderTest(unittest.TestCase):
    def test_full_order(self) -> None:
        calls = [call("read_file"), call("todo_write"), call("edit_file"),
                 call("run_command", "python -m unittest", "Exit code: 0\nOK")]
        score = order_score(calls)
        self.assertEqual(score["order_points"], "4/4")
        self.assertFalse(score["plan_only_after_gate"])

    def test_declined_test_command_is_not_a_test(self) -> None:
        calls = [call("read_file"), call("edit_file"),
                 call("run_command", "cd /project && python -m unittest", "declined", status="denied")]
        score = order_score(calls)
        self.assertFalse(score["tested_after_change"])
        self.assertFalse(score["verified_after_last_change"])

    def test_plan_after_gate_is_marked(self) -> None:
        calls = [call("read_file"), call("edit_file", result="Error: plan first.", status="failed"),
                 call("todo_write"), call("edit_file")]
        score = order_score(calls)
        self.assertTrue(score["planned_before_change"])
        self.assertTrue(score["plan_only_after_gate"])


class ErrorHandlingTest(unittest.TestCase):
    def test_classifies_what_follows_a_failure(self) -> None:
        failing = call("run_command", "pytest", "Exit code: 1\nstats/summary.py line 3")
        calls = [call("read_file", '{"path": "stats/summary.py"}'), failing,
                 call("edit_file", '{"path": "stats/summary.py"}'), failing, failing,
                 call("run_command", "python -m pytest -x", "Exit code: 2"), call("edit_file", '{"path": "other.py"}')]
        counts = error_handling(calls)
        self.assertEqual(counts["informed_change"], 1)
        self.assertEqual(counts["repeated_same_call"], 1)
        self.assertEqual(counts["examined_error"], 1)
        self.assertEqual(counts["guessed"], 1)


class ServiceOutcomeTest(unittest.TestCase):
    def test_telling_or_starting_counts_but_changing_code_does_not(self) -> None:
        told = service_outcome([], f"Start it with python {SERVICE_START_HINT}", False, SERVICE_START_HINT)
        started = service_outcome([call("start_background")], "done", False, SERVICE_START_HINT)
        patched = service_outcome([], f"python {SERVICE_START_HINT}", True, SERVICE_START_HINT)
        self.assertTrue(told["success"])
        self.assertTrue(started["success"])
        self.assertFalse(patched["success"])


class ScenarioProjectTest(unittest.TestCase):
    def test_retest_project_starts_with_two_failing_tests(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            for rel, text in RETEST["files"].items():
                (Path(root) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(root) / rel).write_text(text)
            done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                                  cwd=root, capture_output=True, text=True)
        self.assertIn("failures=2", done.stderr)
