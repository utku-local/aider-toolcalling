"""Reference solution for the todo command line tool specified in README.md.
main(argv) parses the arguments, updates the task file and returns the exit code.
Errors are reported on stderr with the exit codes the README names.
"""

import argparse
import datetime
import json
import pathlib
import sys

PRIORITIES = ("high", "medium", "low")
NO_DUE = "none"
FAR_FUTURE = "9999-12-31"
EXIT_UNKNOWN_ID = 1
EXIT_BAD_DATE = 2


class TodoError(Exception):
    """A user-facing failure with its exit code."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def valid_date(text: str) -> str:
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        raise TodoError(f"invalid date {text}", EXIT_BAD_DATE) from None
    if len(text) != len(FAR_FUTURE):
        raise TodoError(f"invalid date {text}", EXIT_BAD_DATE)
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todo")
    parser.add_argument("--file", default="todo.json")
    parser.add_argument("--today", default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add")
    add.add_argument("title")
    add.add_argument("--priority", choices=PRIORITIES, default="medium")
    add.add_argument("--due", default=None)
    listing = commands.add_parser("list")
    listing.add_argument("--all", action="store_true")
    listing.add_argument("--sort", choices=("id", "priority", "due"), default="id")
    for name in ("done", "delete"):
        commands.add_parser(name).add_argument("id", type=int)
    edit = commands.add_parser("edit")
    edit.add_argument("id", type=int)
    edit.add_argument("--title", default=None)
    edit.add_argument("--priority", choices=PRIORITIES, default=None)
    edit.add_argument("--due", default=None)
    commands.add_parser("stats")
    return parser


def find(data: dict, task_id: int) -> dict:
    for task in data["tasks"]:
        if task["id"] == task_id:
            return task
    raise TodoError(f"no task {task_id}", EXIT_UNKNOWN_ID)


def line(task: dict) -> str:
    due = f" due:{task['due']}" if task["due"] else ""
    return f"[{'x' if task['done'] else ' '}] {task['id']} ({task['priority']}) {task['title']}{due}"


def listing(data: dict, show_all: bool, sort: str) -> list[str]:
    keys = {
        "id": lambda t: t["id"],
        "priority": lambda t: (PRIORITIES.index(t["priority"]), t["id"]),
        "due": lambda t: (t["due"] or FAR_FUTURE, t["due"] is None, t["id"]),
    }
    return [line(t) for t in sorted(data["tasks"], key=keys[sort]) if show_all or not t["done"]]


def apply(args: argparse.Namespace, data: dict, today: str) -> list[str]:
    if args.command == "add":
        due = valid_date(args.due) if args.due else None
        task = {"id": data["next_id"], "title": args.title, "priority": args.priority, "due": due, "done": False}
        data["tasks"].append(task)
        data["next_id"] += 1
        return [f"Added {task['id']}: {task['title']}"]
    if args.command == "list":
        return listing(data, args.all, args.sort)
    if args.command == "stats":
        open_tasks = [t for t in data["tasks"] if not t["done"]]
        overdue = sum(1 for t in open_tasks if t["due"] and t["due"] < today)
        return [f"open: {len(open_tasks)}, done: {len(data['tasks']) - len(open_tasks)}, overdue: {overdue}"]
    task = find(data, args.id)
    if args.command == "done":
        task["done"] = True
        return [f"Done {task['id']}"]
    if args.command == "delete":
        data["tasks"].remove(task)
        return [f"Deleted {task['id']}"]
    if args.due is not None:
        task["due"] = None if args.due == NO_DUE else valid_date(args.due)
    task["title"] = args.title if args.title is not None else task["title"]
    task["priority"] = args.priority or task["priority"]
    return [f"Edited {task['id']}"]


def main(argv: list[str]) -> int:
    """Run one command and return the process exit code."""
    args = build_parser().parse_args(argv)
    path = pathlib.Path(args.file)
    data = json.loads(path.read_text()) if path.exists() else {"next_id": 1, "tasks": []}
    try:
        today = valid_date(args.today) if args.today else datetime.date.today().isoformat()
        lines = apply(args, data, today)
    except TodoError as err:
        print(f"Error: {err}", file=sys.stderr)
        return err.code
    if args.command not in ("list", "stats"):
        path.write_text(json.dumps(data))
    if lines:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
