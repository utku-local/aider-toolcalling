"""Hidden check for the todo-cli task.
It drives todo.py through a subprocess and compares stdout, stderr and exit codes with README.md.
Exit code 0 means the task passed.
"""

import json
import pathlib
import subprocess
import sys

FILE = "check-tasks.json"
pathlib.Path(FILE).unlink(missing_ok=True)


def run(*args: str, code: int = 0, today: str = "2026-11-18") -> str:
    done = subprocess.run(
        [sys.executable, "todo.py", "--file", FILE, "--today", today, *args], capture_output=True, text=True
    )
    assert done.returncode == code, (args, done.returncode, done.stderr)
    return (done.stdout if code == 0 else done.stderr).rstrip("\n")


assert run("list") == ""
assert run("stats") == "open: 0, done: 0, overdue: 0"
assert run("add", "Buy milk") == "Added 1: Buy milk"
assert run("add", "File taxes", "--priority", "high", "--due", "2026-12-01") == "Added 2: File taxes"
assert run("add", "Call mum", "--priority", "low", "--due", "2026-11-10") == "Added 3: Call mum"
assert run("add", "Renew pass", "--priority", "high", "--due", "2026-11-10") == "Added 4: Renew pass"
assert run("list") == (
    "[ ] 1 (medium) Buy milk\n[ ] 2 (high) File taxes due:2026-12-01\n"
    "[ ] 3 (low) Call mum due:2026-11-10\n[ ] 4 (high) Renew pass due:2026-11-10"
)
assert run("list", "--sort", "priority").split("\n")[0::3] == ["[ ] 2 (high) File taxes due:2026-12-01",
                                                               "[ ] 3 (low) Call mum due:2026-11-10"]
assert [line.split()[2] for line in run("list", "--sort", "priority").split("\n")] == ["2", "4", "1", "3"]
assert [line.split()[2] for line in run("list", "--sort", "due").split("\n")] == ["3", "4", "2", "1"]
assert run("stats") == "open: 4, done: 0, overdue: 2"
assert run("stats", today="2026-11-10") == "open: 4, done: 0, overdue: 0"
assert run("done", "3") == "Done 3"
assert run("stats") == "open: 3, done: 1, overdue: 1"
assert "3" not in [line.split()[2] for line in run("list").split("\n")]
assert "[x] 3 (low) Call mum due:2026-11-10" in run("list", "--all").split("\n")
assert run("delete", "2") == "Deleted 2"
assert run("add", "New one") == "Added 5: New one"
assert run("edit", "4", "--due", "none", "--title", "Renew passport") == "Edited 4"
assert run("edit", "1", "--priority", "low", "--due", "2026-11-20") == "Edited 1"
assert run("list", "--sort", "due") == (
    "[ ] 1 (low) Buy milk due:2026-11-20\n[ ] 4 (high) Renew passport\n[ ] 5 (medium) New one"
)
before = pathlib.Path(FILE).read_text()
assert run("done", "7", code=1) == "Error: no task 7"
assert run("delete", "2", code=1) == "Error: no task 2"
assert run("edit", "9", "--title", "x", code=1) == "Error: no task 9"
assert run("add", "Bad", "--due", "2026-02-30", code=2) == "Error: invalid date 2026-02-30"
assert run("edit", "1", "--due", "tomorrow", code=2) == "Error: invalid date tomorrow"
assert pathlib.Path(FILE).read_text() == before
data = json.loads(before)
assert data["next_id"] == 6
assert {"id": 1, "title": "Buy milk", "priority": "low", "due": "2026-11-20", "done": False} in data["tasks"]
assert sorted(task["id"] for task in data["tasks"]) == [1, 3, 4, 5]
