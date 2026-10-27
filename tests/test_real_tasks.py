"""Tests for real-project tasks: file classification, commit selection, mining and task project building.
A small temporary git repository with a buggy commit and a fix commit (source, test and changelog) stands in for a
real project; the task project must hide the fix, keep the new tests and carry no git history.
Validation must accept that commit and reject one whose tests already pass before the fix.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evals.mine_real_tasks import candidate, is_valid
from evals.real_project import build_project, tests_pass, tests_untouched
from evals.real_tasks import (
    RUNNER_PYTEST,
    RUNNER_UNITTEST,
    choose_runner,
    load_tasks,
    qualifies,
    reverted_files,
    save_tasks,
    split_files,
    task_prompt,
)

IDENT = ["-c", "user.email=t@t", "-c", "user.name=t"]
BUGGY = "def double(x):\n    return x + x + 1\n"
FIXED = "def double(x):\n    return x + x\n"
TEST = "import unittest\nfrom calc import double\n\n\nclass T(unittest.TestCase):\n    def test_double(self):\n" \
       "        self.assertEqual(double(2), 4)\n"


def commit(repo: Path, files: dict[str, str], message: str) -> str:
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", *IDENT, "commit", "-qm", message], cwd=repo, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()


class PureLogicTest(unittest.TestCase):
    def test_split_and_revert(self) -> None:
        files = ["lib/a.py", "tests/test_a.py", "tests/data/x.json", "CHANGELOG.md", "b_test.py"]
        self.assertEqual(split_files(files), (("lib/a.py",), ("tests/test_a.py", "b_test.py")))
        self.assertEqual(reverted_files(files), ("lib/a.py", "CHANGELOG.md"))

    def test_qualifies(self) -> None:
        self.assertTrue(qualifies("fix(x): y", ("a.py",), ("test_a.py",), 20))
        self.assertFalse(qualifies("feat: y", ("a.py",), ("test_a.py",), 20))
        self.assertFalse(qualifies("fix: y", ("a.py",), (), 20))
        self.assertFalse(qualifies("fix: y", ("a.py",), ("test_a.py",), 500))
        self.assertFalse(qualifies("fix: y", ("a.py", "b.py", "c.py", "d.py"), ("t.py",), 20))

    def test_runner_choice(self) -> None:
        self.assertEqual(choose_runner(["tests/conftest.py", "a.py"]), RUNNER_PYTEST)
        self.assertEqual(choose_runner(["tests/test_a.py"]), RUNNER_UNITTEST)


class RealProjectTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name, "proj")
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        commit(self.repo, {"calc.py": BUGGY, "CHANGELOG.md": "# Changes\n"}, "add calc")
        self.fix = commit(self.repo, {"calc.py": FIXED, "tests/test_calc.py": TEST,
                                      "CHANGELOG.md": "# Changes\n- double no longer adds one\n"}, "fix: double")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_mining_and_project(self) -> None:
        task = candidate(str(self.repo), self.fix, "fix: double", sys.executable)
        self.assertEqual((task.sources, task.tests), (("calc.py",), ("tests/test_calc.py",)))
        self.assertTrue(is_valid(task))
        self.assertIn("tests/test_calc.py", task_prompt(task))
        self.assertNotIn("adds one", task_prompt(task))

        project = Path(self.tmp.name, "task")
        project.mkdir()
        build_project(task, project, pre_fix=True)
        self.assertEqual((project / "calc.py").read_text(), BUGGY)
        self.assertEqual((project / "CHANGELOG.md").read_text(), "# Changes\n")
        log = subprocess.run(["git", "log", "--oneline"], cwd=project, capture_output=True, text=True).stdout
        self.assertEqual(len(log.splitlines()), 1)
        self.assertFalse(tests_pass(task, project))

        (project / "calc.py").write_text(FIXED)
        self.assertTrue(tests_untouched(task, project) and tests_pass(task, project))
        (project / "tests/test_calc.py").write_text(TEST.replace("4", "5"))
        self.assertFalse(tests_untouched(task, project))

    def test_commit_whose_tests_already_pass_is_rejected(self) -> None:
        sha = commit(self.repo, {"calc.py": FIXED + "\n", "tests/test_more.py": TEST}, "fix: whitespace")
        task = candidate(str(self.repo), sha, "fix: whitespace", sys.executable)
        self.assertFalse(is_valid(task))

    def test_task_file_round_trip(self) -> None:
        task = candidate(str(self.repo), self.fix, "fix: double", sys.executable)
        path = str(Path(self.tmp.name, "tasks.json"))
        save_tasks([task], path)
        self.assertEqual(load_tasks(path), [task])


if __name__ == "__main__":
    unittest.main()
