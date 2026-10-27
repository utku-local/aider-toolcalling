"""Real-project tasks: a past bug-fix commit with its source changes undone and its new tests kept.
This module holds the pure parts: the RealTask record, how a commit's files split into sources and tests, which
commits qualify, and the prompt and test command for a task. Git and test runs live in real_project.py.
A task is valid only when its tests fail on the pre-fix sources and pass at the fix commit.
"""

import json
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any

TEST_PATH = re.compile(r"(^|/)tests?/|(^|/)test_[^/]*\.py$|_test\.py$")
FIX_SUBJECT = re.compile(r"^fix\b", re.IGNORECASE)
PYTHON_SUFFIX = ".py"
MAX_SOURCE_FILES = 3
MAX_CHANGED_LINES = 150
PYTEST_MARKERS = ("conftest.py", "pytest.ini")
RUNNER_PYTEST = "pytest"
RUNNER_UNITTEST = "unittest"


@dataclass(frozen=True)
class RealTask:
    name: str
    repo: str
    commit: str
    subject: str
    sources: tuple[str, ...]
    tests: tuple[str, ...]
    reverted: tuple[str, ...]
    python: str
    runner: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_test_file(path: str) -> bool:
    return bool(TEST_PATH.search(path))


def split_files(paths: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(sources, tests) among the Python files of a commit."""
    python = [p for p in paths if PurePosixPath(p).suffix == PYTHON_SUFFIX]
    return tuple(p for p in python if not is_test_file(p)), tuple(p for p in python if is_test_file(p))


def reverted_files(paths: list[str]) -> tuple[str, ...]:
    """Every changed file except tests: sources, but also changelogs and docs that would describe the fix."""
    return tuple(p for p in paths if not is_test_file(p))


def qualifies(subject: str, sources: tuple[str, ...], tests: tuple[str, ...], changed_lines: int) -> bool:
    """A small fix with both source and test changes."""
    return (
        bool(FIX_SUBJECT.search(subject))
        and 0 < len(sources) <= MAX_SOURCE_FILES
        and bool(tests)
        and changed_lines <= MAX_CHANGED_LINES
    )


def choose_runner(repo_files: list[str]) -> str:
    names = {PurePosixPath(p).name for p in repo_files}
    return RUNNER_PYTEST if names & set(PYTEST_MARKERS) else RUNNER_UNITTEST


def test_command(task: RealTask) -> list[str]:
    if task.runner == RUNNER_PYTEST:
        return [task.python, "-m", "pytest", "-q", *task.tests]
    return [task.python, "-m", "unittest", *task.tests]


def task_prompt(task: RealTask) -> str:
    shown = " ".join(["python", *test_command(task)[1:]])
    return (
        f"These tests fail: {', '.join(task.tests)}. Run them with `{shown}`. "
        "Find the cause in the source code and fix it. Do not modify the test files."
    )


def task_name(repo: str, commit: str) -> str:
    return f"{PurePosixPath(repo).name}-{commit[:7]}"


def save_tasks(tasks: list[RealTask], path: str) -> None:
    with open(path, "w") as handle:
        json.dump([t.as_dict() for t in tasks], handle, indent=2)


def load_tasks(path: str) -> list[RealTask]:
    with open(path) as handle:
        return [
            RealTask(**{**raw, **{key: tuple(raw[key]) for key in ("sources", "tests", "reverted")}})
            for raw in json.load(handle)
        ]
