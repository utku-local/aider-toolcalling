"""Mines real-project tasks from a repository's bug-fix commits and writes the valid ones to a JSON file.
A commit qualifies when it is a small fix touching both Python sources and tests; it becomes a task only when its
tests fail on the pre-fix project and pass on the fix commit, both checked with the given interpreter.
Run it as: python -m evals.mine_real_tasks --repo PATH --python PY [--count N] [--scan N] [--out FILE].
"""

import argparse
import tempfile
from pathlib import Path
from typing import Optional

from evals.real_project import build_project, changed_files, fix_commits, tests_pass, tree_files
from evals.real_tasks import (
    RealTask,
    choose_runner,
    qualifies,
    reverted_files,
    save_tasks,
    split_files,
    task_name,
)

REAL_DIR = Path(__file__).resolve().parent / "real"
DEFAULT_COUNT = 10
DEFAULT_SCAN = 300


def candidate(repo: str, sha: str, subject: str, python: str) -> Optional[RealTask]:
    files, lines = changed_files(repo, sha)
    sources, tests = split_files(files)
    if not qualifies(subject, sources, tests, lines):
        return None
    return RealTask(
        name=task_name(repo, sha), repo=repo, commit=sha, subject=subject, sources=sources, tests=tests,
        reverted=reverted_files(files), python=python, runner=choose_runner(tree_files(repo, sha)),
    )


def is_valid(task: RealTask) -> bool:
    """Tests must fail with the fix undone and pass with it applied."""
    with tempfile.TemporaryDirectory() as before, tempfile.TemporaryDirectory() as after:
        build_project(task, Path(before), pre_fix=True)
        if tests_pass(task, Path(before)):
            return False
        build_project(task, Path(after), pre_fix=False)
        return tests_pass(task, Path(after))


def mine(repo: str, python: str, count: int, scan: int) -> list[RealTask]:
    found: list[RealTask] = []
    for sha, subject in fix_commits(repo, scan):
        task = candidate(repo, sha, subject, python)
        if task is None:
            continue
        valid = is_valid(task)
        print(f"{'valid  ' if valid else 'skipped'} {task.name} {subject[:70]}")
        if valid:
            found.append(task)
        if len(found) >= count:
            break
    return found


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mine real-project tasks from bug-fix commits.")
    parser.add_argument("--repo", required=True, help="Path to a git repository")
    parser.add_argument("--python", required=True, help="Interpreter that can run the repo's tests")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="Tasks to keep (default: 10)")
    parser.add_argument("--scan", type=int, default=DEFAULT_SCAN, help="Commits to scan (default: 300)")
    parser.add_argument("--out", default="", help="Output JSON (default: evals/real/<repo>.json)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = str(Path(args.repo).expanduser().resolve())
    tasks = mine(repo, args.python, args.count, args.scan)
    REAL_DIR.mkdir(exist_ok=True)
    out = args.out or str(REAL_DIR / f"{Path(repo).name}.json")
    save_tasks(tasks, out)
    print(f"{len(tasks)} task(s) written to {out}")


if __name__ == "__main__":
    main()
