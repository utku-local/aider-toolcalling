"""Tests for the expert evaluation fixtures: every task loads, and its hidden check judges correctly.
For each task the check must fail on the starting project and pass once the reference solution is applied, so a
task can neither pass untouched nor be unsolvable.
The checks run in a temporary copy through the eval runner's own run_check, with no agent or model involved.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from evals.run_evals import run_check
from evals.tasks_expert import SOLUTION_DIR, ExpertTask, load_expert_tasks, solution_removes

MINIMUM_TASKS = 8


def build(task: ExpertTask, root: Path, solved: bool) -> None:
    folder = Path(task.origin).parent
    shutil.copytree(task.origin, root, dirs_exist_ok=True)
    if solved:
        for rel in solution_removes(folder):
            (root / rel).unlink()
        shutil.copytree(folder / SOLUTION_DIR, root, dirs_exist_ok=True)


class ExpertTasksTest(unittest.TestCase):
    def test_tasks_load(self) -> None:
        tasks = load_expert_tasks()
        self.assertGreaterEqual(len(tasks), MINIMUM_TASKS)
        for task in tasks:
            self.assertTrue(task.prompt and task.check and task.files, task.name)
            self.assertFalse([path for path in task.files if "__pycache__" in path], task.name)

    def test_check_fails_before_and_passes_with_the_solution(self) -> None:
        for task in load_expert_tasks():
            for solved in (False, True):
                with self.subTest(task=task.name, solved=solved), tempfile.TemporaryDirectory() as tmp:
                    build(task, Path(tmp), solved)
                    self.assertEqual(run_check(task, Path(tmp)), solved)


if __name__ == "__main__":
    unittest.main()
