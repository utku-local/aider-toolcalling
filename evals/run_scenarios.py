"""Runs the behaviour scenarios against the agent and writes one scored JSON summary per run.
Each run builds a fresh git project from evals.scenarios, runs the patched agent with the same flags for every
model (only the model and the seed change), and scores its saved session with evals.scenario_scoring.
Run it with the aider-chat interpreter from the repo root: python -m evals.run_scenarios [--model M] [--repeat N].
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

from evals.run_evals import GIT_IDENTITY, REPO_ROOT, RESULTS_DIR
from evals.scenario_scoring import Call, error_handling, order_score, service_outcome, token_counts
from evals.scenarios import SCENARIOS, SERVICE_CODE_FILES, SERVICE_START_HINT

TIMEOUT_SECONDS = 1500
FIRST_SEED = 1
DEFAULT_REPEAT = 3
MIN_ANSWER_CHARS = 20
ANSWER_TAIL_CHARS = 600
SESSION_FILE = ".aider.agent-session.json"
SENT_BACK = "Sending the answer back"
TIMEOUT_MARK = "\nTIMEOUT"
AGENT_FLAGS = ("--yes-always", "--no-auto-commits", "--no-auto-lint", "--no-check-update", "--analytics-disable")
AGENT_CONFIG = {
    "sandbox": True,
    "commands": {"allow": [{"program": p} for p in
                           ("python", "python3", "unittest", "pytest", "lsof", "pgrep", "curl", "cat", "ls")]},
}


def make_project(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="scenario-"))
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    (root / ".aider-agent.json").write_text(json.dumps(AGENT_CONFIG))
    for args in (["init", "-q"], ["add", "-A"], [*GIT_IDENTITY, "commit", "-qm", "scenario"]):
        subprocess.run(["git", *args], cwd=root, check=True)
    return root


def run_agent(root: Path, prompt: str, model: str, seed: int) -> tuple[str, float]:
    command = [sys.executable, "-m", "aider.agent_main", *AGENT_FLAGS, "--seed", str(seed), "--message", prompt]
    if model:
        command += ["--model", model]
    started = time.monotonic()
    try:
        done = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
                              env={**os.environ, "PYTHONPATH": str(REPO_ROOT)}, stdin=subprocess.DEVNULL)
        output = done.stdout + done.stderr
    except subprocess.TimeoutExpired as err:
        output = (err.stdout if isinstance(err.stdout, str) else "") + TIMEOUT_MARK
    return output, time.monotonic() - started


def load_session(root: Path) -> tuple[list[Call], str]:
    """Calls with full results and statuses, and the final answer, from the agent's saved session."""
    path = root / SESSION_FILE
    if not path.is_file():
        return [], ""
    data = json.loads(path.read_text())
    calls = [{"tool": r["tool"], "args": r["arguments"], "result": r["result"], "status": r["status"]}
             for r in data["ledger"]]
    answers = [m.get("content") or "" for m in data["messages"]
               if m.get("role") == "assistant" and len(m.get("content") or "") > MIN_ANSWER_CHARS]
    return calls, answers[-1] if answers else ""


def unit_tests_pass(root: Path) -> bool:
    done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=root,
                          capture_output=True, text=True)
    return done.returncode == 0


def task_outcome(name: str, root: Path, calls: list[Call], answer: str) -> dict:
    """Success judged from the project itself, never from the agent's own claim."""
    if name == "service":
        changed = subprocess.run(["git", "diff", "--quiet", "--", *SERVICE_CODE_FILES], cwd=root).returncode != 0
        return service_outcome(calls, answer, changed, SERVICE_START_HINT)
    passing = unit_tests_pass(root)
    if name == "planning":
        tagged = "tag" in (root / "tests" / "test_cli.py").read_text()
        return {"tests_pass": passing, "added_tag_tests": tagged, "success": passing and tagged}
    return {"tests_pass": passing, "success": passing}


def run_once(name: str, model: str, seed: int, out: Path) -> dict:
    scenario = SCENARIOS[name]
    root = make_project(scenario["files"])
    log, seconds = run_agent(root, scenario["prompt"], model, seed)
    (out / f"{name}-seed{seed}.log").write_text(log)
    calls, answer = load_session(root)
    sent, received = token_counts(log)
    return {"scenario": name, "seed": seed, "model": model or "default", "seconds": round(seconds, 1),
            "tokens_sent": sent, "tokens_received": received, "calls": len(calls),
            "sequence": [c["tool"] for c in calls], "order": order_score(calls), "errors": error_handling(calls),
            "task": task_outcome(name, root, calls, answer), "sent_back": SENT_BACK in log,
            "answer": answer[-ANSWER_TAIL_CHARS:]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="", help="Model name passed to the agent (default: aider config)")
    parser.add_argument("--only", default="", help="Run one scenario: " + ", ".join(SCENARIOS))
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT, help="Runs per scenario, seeds 1..N")
    parser.add_argument("--out", default="", help="Output folder (default: evals/results/scenarios-<time>)")
    args = parser.parse_args()
    out = Path(args.out) if args.out else RESULTS_DIR / f"scenarios-{datetime.now():%Y%m%d-%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    print(f"Results: {out}", flush=True)
    for seed in range(FIRST_SEED, FIRST_SEED + args.repeat):
        for name in SCENARIOS:
            if args.only and name != args.only:
                continue
            summary = run_once(name, args.model, seed, out)
            (out / f"{name}-seed{seed}.json").write_text(json.dumps(summary, indent=2))
            print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
