"""Runs the evaluation tasks against the agent mode and records one JSON line per task.
Each task gets a fresh temporary git repo; the patched Aider runs with --agent --yes-always, so edits are approved
and shell commands are not, then the task's check script decides pass or fail.
Run it with the aider-chat interpreter from the repo root: python -m evals.run_evals [--tasks a,b] [--model M].
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from evals.metrics import TaskResult, parse_metrics, summarize
from evals.tasks import TASKS, EvalTask

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "evals" / "results"
DEFAULT_TIMEOUT_SECONDS = 900
CHECK_TIMEOUT_SECONDS = 60
GIT_IDENTITY = ("-c", "user.email=eval@localhost", "-c", "user.name=eval")
AIDER_FLAGS = (
    "--agent",
    "--yes-always",
    "--no-auto-commits",
    "--no-check-update",
    "--no-show-release-notes",
    "--analytics-disable",
    "--no-gitignore",
    "--no-auto-lint",
    "--no-pretty",
)
CHECK_FILE = "_eval_check.py"


def setup_project(task: EvalTask, root: Path) -> None:
    for rel, text in task.files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", *GIT_IDENTITY, "commit", "-qm", "task"], cwd=root, check=True)


def run_agent(task: EvalTask, root: Path, model: str, timeout: int) -> tuple[str, float]:
    command = [sys.executable, "-m", "aider", *AIDER_FLAGS, "--message", task.prompt]
    if model:
        command += ["--model", model]
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    started = time.monotonic()
    try:
        done = subprocess.run(
            command, cwd=root, env=env, capture_output=True, text=True, errors="replace", timeout=timeout
        )
        output = done.stdout + done.stderr
    except subprocess.TimeoutExpired as err:
        output = f"{err.stdout or ''}{err.stderr or ''}\n[timed out after {timeout}s]"
    return output, time.monotonic() - started


def run_check(task: EvalTask, root: Path) -> bool:
    (root / CHECK_FILE).write_text(task.check)
    try:
        done = subprocess.run(
            [sys.executable, CHECK_FILE], cwd=root, capture_output=True, timeout=CHECK_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


def run_task(task: EvalTask, model: str, timeout: int) -> TaskResult:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        setup_project(task, root)
        output, seconds = run_agent(task, root, model, timeout)
        return TaskResult(task.name, run_check(task, root), round(seconds, 1), parse_metrics(output))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the agent evaluation set.")
    parser.add_argument("--tasks", default="", help="Comma-separated task names (default: all)")
    parser.add_argument("--model", default="", help="Model name passed to aider (default: aider config)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Seconds per task")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    wanted = {name for name in args.tasks.split(",") if name}
    tasks = [t for t in TASKS if not wanted or t.name in wanted]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    print(f"Repo root: {REPO_ROOT}\nResults: {out_path}")
    results = []
    with open(out_path, "w") as handle:
        for task in tasks:
            result = run_task(task, args.model, args.timeout)
            results.append(result)
            handle.write(json.dumps(result.as_dict()) + "\n")
            handle.flush()
            print(f"{'PASS' if result.passed else 'FAIL'} {task.name} ({result.seconds}s)")
    print(json.dumps(summarize(results), indent=2))


if __name__ == "__main__":
    main()
