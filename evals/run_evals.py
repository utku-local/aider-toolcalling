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

from evals.metrics import TaskResult, finished_runs, parse_metrics, summarize
from evals.real_project import build_project, tests_pass, tests_untouched
from evals.real_tasks import RealTask, load_tasks, task_prompt
from aider.native_tools_shell import as_text
from evals.tasks import TASKS, EvalTask
from evals.tasks_expert import ORIGIN_ENV, ExpertTask, load_expert_tasks
from evals.tasks_hard import HARD_TASKS

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "evals" / "results"
DEFAULT_TIMEOUT_SECONDS = 900
TASK_SETS = {"basic": TASKS, "hard": HARD_TASKS, "all": TASKS + HARD_TASKS}
# The expert set is read from fixture folders when it is selected, so importing this module touches no files.
EXPERT_SET = "expert"
SET_CHOICES = (*sorted(TASK_SETS), EXPERT_SET)
PROCESS_ENV = dict(os.environ)
DEFAULT_SET = "basic"
DEFAULT_REPEAT = 1
# Run k uses seed DEFAULT_SEED_BASE + k: repeats sample independently, and a rerun reproduces a run.
DEFAULT_SEED_BASE = 1000
CHECK_TIMEOUT_SECONDS = 60
AFTER_TIMEOUT_LIMIT_SECONDS = 600
CHECK_OUTPUT_CHARS = 2000
CHECK_HEADING = "[eval check]"
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


def run_agent(task: EvalTask, root: Path, model: str, timeout: int, seed: int) -> tuple[str, float]:
    prompt = task_prompt(task) if isinstance(task, RealTask) else task.prompt
    command = [sys.executable, "-m", "aider", *AIDER_FLAGS, "--seed", str(seed), "--message", prompt]
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


def check_outcome(task: EvalTask, root: Path) -> tuple[bool, str]:
    """Run the task's check in the project; returns whether it passed and the end of what it printed.

    An expert check also gets the pristine project as EVAL_ORIGIN. The output names the assertion that failed,
    which is the only trace of why once the temporary project is gone."""
    (root / CHECK_FILE).write_text(task.check)
    env = {**PROCESS_ENV, ORIGIN_ENV: task.origin} if isinstance(task, ExpertTask) else None
    try:
        done = subprocess.run(
            [sys.executable, CHECK_FILE], cwd=root, capture_output=True, timeout=CHECK_TIMEOUT_SECONDS, env=env,
            text=True, errors="replace",
        )
    except subprocess.TimeoutExpired:
        return False, f"check timed out after {CHECK_TIMEOUT_SECONDS}s"
    return done.returncode == 0, (done.stdout + done.stderr)[-CHECK_OUTPUT_CHARS:]


def run_check(task: EvalTask, root: Path) -> bool:
    return check_outcome(task, root)[0]


def check_note(passed: bool, detail: str) -> str:
    """The lines added to a task's log after the agent's output: the check's verdict and what it printed."""
    return f"\n{CHECK_HEADING} {'passed' if passed else 'failed'}\n{detail.strip()}\n"


def setup_real_project(task: RealTask, root: Path, sandbox: bool) -> None:
    build_project(task, root, pre_fix=True)
    if sandbox:
        (root / AGENT_CONFIG_FILE).write_text(json.dumps(SANDBOX_CONFIG))


def check_real(task: RealTask, root: Path) -> bool:
    """The fix's tests pass and the agent left them unchanged."""
    return tests_untouched(task, root) and tests_pass(task, root)


def run_task(
    task: EvalTask, model: str, timeout: int, sandbox: bool, log_path: Path, seed: int
) -> TaskResult:
    """Run one task; the agent's full output is kept at `log_path` for diagnosis."""
    real = isinstance(task, RealTask)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        if real:
            setup_real_project(task, root, sandbox)
        else:
            setup_project(task, root, sandbox)
        output, seconds = run_agent(task, root, model, timeout, seed)
        passed, detail = (check_real(task, root), "") if real else check_outcome(task, root)
        log_path.write_text(output + check_note(passed, detail))
        return TaskResult(task.name, passed, round(seconds, 1), parse_metrics(output))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the agent evaluation set.")
    parser.add_argument("--tasks", default="", help="Comma-separated task names (default: the whole set)")
    parser.add_argument("--set", default=DEFAULT_SET, choices=SET_CHOICES, help="Task set (default: basic)")
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT, help="Runs per task (default: 1)")
    parser.add_argument(
        "--seed-base", type=int, default=DEFAULT_SEED_BASE, help="Run k uses seed base + k (default: 1000)"
    )
    parser.add_argument("--real", default="", help="Real-project task file from mine_real_tasks (replaces --set)")
    parser.add_argument("--model", default="", help="Model name passed to aider (default: aider config)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Seconds per task")
    parser.add_argument(
        "--resume", default="",
        help="Results .jsonl of an earlier run: its finished (task, run) pairs are skipped and new ones appended",
    )
    parser.add_argument(
        "--after-timeout", default="",
        help="Shell command run after a task that hit --timeout, before the next task, for example a restart of "
        "the model server, which otherwise keeps generating the killed task's last request (default: none)",
    )
    parser.add_argument(
        "--sandbox", action="store_true", default=False,
        help="Sandbox commands and allow python/pytest without approval (default: False)",
    )
    return parser.parse_args()


def settle_after_timeout(seconds: float, timeout: int, command: str) -> bool:
    """Run `command` when a task used its whole time limit; returns whether it ran.

    A task killed at the limit leaves its last request generating on a local server, which starves the next task
    (measured: a task that received no reply in 2,400 s). The command's own failure or overrun is only reported."""
    if not command or seconds < timeout:
        return False
    print(f"Task hit the time limit; running: {command}")
    try:
        done = subprocess.run(command, shell=True, timeout=AFTER_TIMEOUT_LIMIT_SECONDS)
        if done.returncode:
            print(f"The after-timeout command exited with {done.returncode}")
    except subprocess.TimeoutExpired:
        print(f"The after-timeout command did not finish in {AFTER_TIMEOUT_LIMIT_SECONDS}s")
    return True


def results_file(resume: str) -> tuple[Path, dict[tuple[str, int], TaskResult]]:
    """Where results go and what is already there: a new timestamped file, or the file being resumed."""
    if not resume:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        return RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl", {}
    path = Path(resume).resolve()
    return path, finished_runs(path.read_text().splitlines())


def main() -> None:
    args = parse_args()
    wanted = {name for name in args.tasks.split(",") if name}
    if args.real:
        pool = load_tasks(args.real)
    else:
        pool = load_expert_tasks() if args.set == EXPERT_SET else TASK_SETS[args.set]
    tasks = [t for t in pool if not wanted or t.name in wanted]
    out_path, done = results_file(args.resume)
    logs_dir = out_path.with_suffix("")
    logs_dir.mkdir(exist_ok=True)
    print(f"Repo root: {REPO_ROOT}\nResults: {out_path}\nAgent output: {logs_dir}\nSandbox: {args.sandbox}")
    results = list(done.values())
    with open(out_path, "a") as handle:
        for run in range(1, args.repeat + 1):
            for task in tasks:
                if (task.name, run) in done:
                    print(f"SKIP {task.name} run {run} (already in the results file)")
                    continue
                log_path = logs_dir / f"{task.name}-run{run}.log"
                result = run_task(task, args.model, args.timeout, args.sandbox, log_path, args.seed_base + run)
                results.append(result)
                handle.write(json.dumps({**result.as_dict(), "run": run}) + "\n")
                handle.flush()
                print(f"{'PASS' if result.passed else 'FAIL'} {task.name} run {run} ({result.seconds}s)")
                settle_after_timeout(result.seconds, args.timeout, args.after_timeout)
    print(json.dumps(summarize(results), indent=2))


if __name__ == "__main__":
    main()
