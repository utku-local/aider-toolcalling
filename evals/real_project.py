"""Git and test-run adapter for real-project tasks: reads commits, builds task projects and runs their tests.
A task project is a fresh repository with no history, built from the fix commit's tree with every non-test file
the fix touched put back to its pre-fix version, so the agent cannot read the answer from git.
Validation keeps a commit only if its tests fail on that project and pass on the fix commit's own tree.
"""

import io
import subprocess
import tarfile
from pathlib import Path
from typing import Optional

from evals.real_tasks import RealTask, test_command

GIT_IDENTITY = ("-c", "user.email=eval@localhost", "-c", "user.name=eval")
TEST_TIMEOUT_SECONDS = 300
FIELD_SEPARATOR = "\x1f"


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def fix_commits(repo: str, limit: int) -> list[tuple[str, str]]:
    """(sha, subject) of the newest commits, newest first; filtering happens in the caller."""
    log = git(repo, "log", "--no-merges", f"-n{limit}", f"--format=%H{FIELD_SEPARATOR}%s")
    return [tuple(line.split(FIELD_SEPARATOR, 1)) for line in log.splitlines() if line]


def changed_files(repo: str, commit: str) -> tuple[list[str], int]:
    """Files changed by `commit` and the number of added plus removed lines."""
    numstat = git(repo, "show", "--numstat", "--format=", commit)
    files, lines = [], 0
    for row in numstat.splitlines():
        added, removed, path = row.split("\t", 2)
        files.append(path)
        lines += int(added) + int(removed) if added.isdigit() and removed.isdigit() else 0
    return files, lines


def tree_files(repo: str, commit: str) -> list[str]:
    return git(repo, "ls-tree", "-r", "--name-only", commit).splitlines()


def extract_tree(repo: str, commit: str, dest: Path) -> None:
    archive = subprocess.run(["git", "-C", repo, "archive", commit], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dest)


def file_at(repo: str, commit: str, path: str) -> Optional[bytes]:
    done = subprocess.run(["git", "-C", repo, "show", f"{commit}:{path}"], capture_output=True)
    return done.stdout if done.returncode == 0 else None


def restore_pre_fix(task: RealTask, dest: Path) -> None:
    for path in task.reverted:
        before = file_at(task.repo, f"{task.commit}^", path)
        target = dest / path
        if before is None:
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(before)


def build_project(task: RealTask, dest: Path, pre_fix: bool) -> None:
    """Fresh history-free repo at the fix commit, with the fix undone when `pre_fix`."""
    extract_tree(task.repo, task.commit, dest)
    if pre_fix:
        restore_pre_fix(task, dest)
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    subprocess.run(["git", *GIT_IDENTITY, "commit", "-qm", "task"], cwd=dest, check=True)


def tests_pass(task: RealTask, dest: Path) -> bool:
    try:
        done = subprocess.run(test_command(task), cwd=dest, capture_output=True, timeout=TEST_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


def tests_untouched(task: RealTask, dest: Path) -> bool:
    return all((dest / path).read_bytes() == file_at(task.repo, task.commit, path) for path in task.tests)
