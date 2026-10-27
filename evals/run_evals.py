"""Runs the evaluation tasks against the agent mode and records one JSON line per task.
Each task gets a fresh temporary git repo; the patched Aider runs with --agent --yes-always, so edits are approved
and shell commands are not, then the task's check script decides pass or fail.
Run it with the aider-chat interpreter from the repo root: python -m evals.run_evals [--tasks a,b] [--model M].
With --sandbox each project gets a .aider-agent.json that sandboxes commands and allows python and pytest, so the
agent can verify its work without approval inside the sandbox.
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
from evals.tasks_hard import HARD_TASKS

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "evals" / "results"
DEFAULT_TIMEOUT_SECONDS = 900
TASK_SETS = {"basic": TASKS, "hard": HARD_TASKS, "all": TASKS + HARD_TASKS}
DEFAULT_SET = "basic"
DEFAULT_REPEAT = 1
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
AGENT_CONFIG_FILE = ".aider-agent.json"
SANDBOX_CONFIG = {
    "sandbox": True,
    "commands": {"allow": [{"program": "python"}, {"program": "python3"}, {"program": "pytest"}]},
}


def setup_project(task: EvalTask, root: Path, sandbox: bool) -> None:
    if sandbox:
        (root / AGENT_CONFIG_FILE).write_text(json.dumps(SANDBOX_CONFIG))
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


def run_task(task: EvalTask, model: str, timeout: int, sandbox: bool) -> TaskResult:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        setup_project(task, root, sandbox)
        output, seconds = run_agent(task, root, model, timeout)
        return TaskResult(task.name, run_check(task, root), round(seconds, 1), parse_metrics(output))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the agent evaluation set.")
    parser.add_argument("--tasks", default="", help="Comma-separated task names (default: the whole set)")
    parser.add_argument("--set", default=DEFAULT_SET, choices=sorted(TASK_SETS), help="Task set (default: basic)")
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT, help="Runs per task (default: 1)")
    parser.add_argument("--model", default="", help="Model name passed to aider (default: aider config)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Seconds per task")
    parser.add_argument(
        "--sandbox", action="store_true", default=False,
        help="Sandbox commands and allow python/pytest without approval (default: False)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    wanted = {name for name in args.tasks.split(",") if name}
    tasks = [t for t in TASK_SETS[args.set] if not wanted or t.name in wanted]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    print(f"Repo root: {REPO_ROOT}\nResults: {out_path}\nSandbox: {args.sandbox}")
    results = []
    with open(out_path, "w") as handle:
        for run in range(1, args.repeat + 1):
            for task in tasks:
                result = run_task(task, args.model, args.timeout, args.sandbox)
                results.append(result)
                handle.write(json.dumps({**result.as_dict(), "run": run}) + "\n")
                handle.flush()
                print(f"{'PASS' if result.passed else 'FAIL'} {task.name} run {run} ({result.seconds}s)")
    print(json.dumps(summarize(results), indent=2))


if __name__ == "__main__":
    main()
