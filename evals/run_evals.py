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
from evals.real_project import build_project, tests_pass, tests_untouched
from evals.real_tasks import RealTask, load_tasks, task_prompt
from aider.native_tools_shell import as_text
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
    "commands": {
        "allow": [{"program": "python"}, {"program": "python3"}, {"program": "pytest"}, {"program": "unittest"}]
    },
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
    prompt = task_prompt(task) if isinstance(task, RealTask) else task.prompt
    command = [sys.executable, "-m", "aider", *AIDER_FLAGS, "--message", prompt]
    if model:
        command += ["--model", model]
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    if isinstance(task, RealTask):
        # `python` in the agent's commands should be the interpreter that can run the project's tests.
        env["PATH"] = f"{Path(task.python).parent}{os.pathsep}{env.get('PATH', '')}"
    started = time.monotonic()
    try:
        done = subprocess.run(
            command, cwd=root, env=env, capture_output=True, text=True, errors="replace", timeout=timeout
        )
        output = done.stdout + done.stderr
    except subprocess.TimeoutExpired as err:
        output = f"{as_text(err.stdout)}{as_text(err.stderr)}\n[timed out after {timeout}s]"
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


def setup_real_project(task: RealTask, root: Path, sandbox: bool) -> None:
    build_project(task, root, pre_fix=True)
    if sandbox:
        (root / AGENT_CONFIG_FILE).write_text(json.dumps(SANDBOX_CONFIG))


def check_real(task: RealTask, root: Path) -> bool:
    """The fix's tests pass and the agent left them unchanged."""
    return tests_untouched(task, root) and tests_pass(task, root)


def run_task(task: EvalTask, model: str, timeout: int, sandbox: bool, log_path: Path) -> TaskResult:
    """Run one task; the agent's full output is kept at `log_path` for diagnosis."""
    real = isinstance(task, RealTask)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        if real:
            setup_real_project(task, root, sandbox)
        else:
            setup_project(task, root, sandbox)
        output, seconds = run_agent(task, root, model, timeout)
        log_path.write_text(output)
        passed = check_real(task, root) if real else run_check(task, root)
        return TaskResult(task.name, passed, round(seconds, 1), parse_metrics(output))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the agent evaluation set.")
    parser.add_argument("--tasks", default="", help="Comma-separated task names (default: the whole set)")
    parser.add_argument("--set", default=DEFAULT_SET, choices=sorted(TASK_SETS), help="Task set (default: basic)")
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT, help="Runs per task (default: 1)")
    parser.add_argument("--real", default="", help="Real-project task file from mine_real_tasks (replaces --set)")
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
    pool = load_tasks(args.real) if args.real else TASK_SETS[args.set]
    tasks = [t for t in pool if not wanted or t.name in wanted]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    logs_dir = out_path.with_suffix("")
    logs_dir.mkdir()
    print(f"Repo root: {REPO_ROOT}\nResults: {out_path}\nAgent output: {logs_dir}\nSandbox: {args.sandbox}")
    results = []
    with open(out_path, "w") as handle:
        for run in range(1, args.repeat + 1):
            for task in tasks:
                result = run_task(task, args.model, args.timeout, args.sandbox, logs_dir / f"{task.name}-run{run}.log")
                results.append(result)
                handle.write(json.dumps({**result.as_dict(), "run": run}) + "\n")
                handle.flush()
                print(f"{'PASS' if result.passed else 'FAIL'} {task.name} run {run} ({result.seconds}s)")
    print(json.dumps(summarize(results), indent=2))


if __name__ == "__main__":
    main()
