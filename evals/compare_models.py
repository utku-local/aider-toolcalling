"""Builds a model comparison in Markdown from eval result files and scenario folders.
For each model it reports success, time and tokens per successful task and how often an answer was sent back to
verify, and for the scenarios the order points, unprompted planning and recovery after failures.
Usage: python -m evals.compare_models --run 27B:hard:STAMP ... --scenarios 27B:DIR ...; STAMP is a results name.
"""

import argparse
import json
from pathlib import Path

from evals.run_evals import RESULTS_DIR
from evals.run_scenarios import SENT_BACK

SEPARATOR = ":"
KILO = 1000


def eval_line(model: str, set_name: str, stamp: str) -> str:
    path = RESULTS_DIR / f"{stamp}.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    passed = sum(r["passed"] for r in rows)
    seconds = sum(r["seconds"] for r in rows)
    tokens = sum(r["metrics"]["tokens_sent"] + r["metrics"]["tokens_received"] for r in rows)
    logs = list((RESULTS_DIR / stamp).glob("*.log"))
    sent_back = sum(SENT_BACK in log.read_text(errors="replace") for log in logs)
    per = passed or 1
    return (f"| {model} | {set_name} | {passed}/{len(rows)} | {seconds / per:.0f} s | {tokens / per / KILO:.0f}k | "
            f"{sent_back}/{len(rows)} |")


def scenario_lines(model: str, folder: Path) -> list[str]:
    rows = [json.loads(p.read_text()) for p in sorted(folder.glob("*-seed*.json"))]
    lines = []
    for name in sorted({r["scenario"] for r in rows}):
        runs = [r for r in rows if r["scenario"] == name]
        success = sum(r["task"]["success"] for r in runs)
        order = sum(int(r["order"]["order_points"].split("/")[0]) for r in runs)
        unprompted = sum(r["order"]["planned_before_change"] and not r["order"]["plan_only_after_gate"] for r in runs)
        failures = sum(r["errors"]["failures"] for r in runs)
        recovered = sum(r["errors"]["examined_error"] + r["errors"]["informed_change"] for r in runs)
        per = success or 1
        seconds = sum(r["seconds"] for r in runs) / per
        tokens = sum(r["tokens_sent"] + r["tokens_received"] for r in runs) / per / KILO
        lines.append(f"| {model} | {name} | {success}/{len(runs)} | {order} | {unprompted}/{len(runs)} | "
                     f"{recovered}/{failures} | {seconds:.0f} s | {tokens:.0f}k |")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", default=[], help="MODEL:SET:STAMP of an evals.run_evals result")
    parser.add_argument("--scenarios", action="append", default=[], help="MODEL:FOLDER of evals.run_scenarios")
    args = parser.parse_args()
    if args.run:
        print("| Model | Set | Passed | Time per success | Tokens per success | Sent back to verify |")
        print("|---|---|---|---|---|---|")
        for spec in args.run:
            model, set_name, stamp = spec.split(SEPARATOR, 2)
            print(eval_line(model, set_name, stamp))
        print()
    if args.scenarios:
        print("| Model | Scenario | Success | Order points | Planned unprompted | Recovered / failures | "
              "Time per success | Tokens per success |")
        print("|---|---|---|---|---|---|---|---|")
        for spec in args.scenarios:
            model, folder = spec.split(SEPARATOR, 1)
            print("\n".join(scenario_lines(model, Path(folder))))


if __name__ == "__main__":
    main()
