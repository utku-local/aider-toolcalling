"""Hidden check for the circular-import task.
It runs the report on data.json and on a second data set, and imports each module in a fresh interpreter.
Exit code 0 means the task passed.
"""

import json
import os
import pathlib
import subprocess
import sys

ORIGIN = os.environ.get("EVAL_ORIGIN", "")
if ORIGIN:
    assert pathlib.Path("data.json").read_text() == pathlib.Path(ORIGIN, "data.json").read_text(), "data.json changed"


def report(path: str) -> str:
    done = subprocess.run([sys.executable, "-m", "app", "report", path], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


expected = "globex      1,250.00\nacme          310.50\ninitech        99.90\nTOTAL       1,660.40\n"
assert report("data.json") == expected, report("data.json")
for module in ("app.models", "app.services", "app"):
    done = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True)
    assert done.returncode == 0, (module, done.stderr)

other = [
    {"customer": "Zed", "region": "us", "net": "10"},
    {"customer": "abe", "region": "us", "net": "10.00"},
    {"customer": "ZED", "region": "uk", "net": "1000000", "void": False},
    {"customer": "mid", "region": "eu", "net": "0.5", "void": True},
]
pathlib.Path("check-data.json").write_text(json.dumps(other))
assert report("check-data.json") == "zed       1,200,010.00\nabe            10.00\nTOTAL     1,200,020.00\n", report(
    "check-data.json")
