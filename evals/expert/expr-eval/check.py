"""Hidden check for the expr-eval task.
It restores the visible tests, runs them, then checks the parts of SPEC.md the visible tests leave out.
Exit code 0 means the task passed.
"""

import os
import pathlib
import re
import shutil
import subprocess
import sys

ORIGIN = os.environ.get("EVAL_ORIGIN", "")
if ORIGIN:
    shutil.copy(pathlib.Path(ORIGIN) / "tests" / "test_evaluator.py", "tests/test_evaluator.py")
tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], capture_output=True)
assert tests.returncode == 0, tests.stderr.decode()

from calc import EvalError, evaluate  # noqa: E402

source = pathlib.Path("calc/evaluator.py").read_text()
assert not re.search(r"(?<![\w.])(eval|exec|compile)\(|^\s*(import|from) ast\b", source, re.MULTILINE)

VALUES = {
    "2 ** -1": 0.5, "-7 % 3": 2, "1e3 + .5": 1000.5, "2.5e-2 * 4": 0.1, "--3": 3, "-(2 + 3) * 2": -10,
    "min(4, 2, 8) + max(1)": 3, "sqrt(16) + abs(2 - 5)": 7.0, "2 * (3 + (4 - 1)) // 4": 3, "10 - 4 - 3": 3,
    "2 ** 2 ** 0": 2, "-2 ** -2": -0.25, "max (1, 2)": 2, " 1+1 ": 2,
}
for text, expected in VALUES.items():
    got = evaluate(text)
    assert got == expected and type(got) is type(expected), (text, got)
assert evaluate("a * (b + _c1)", {"a": 2, "b": 3, "_c1": 4}) == 14

POSITIONS = {
    "": 0, "(1 + 2": 6, "1 +": 3, "1 2": 2, "(1))": 3, "1 + foo": 4, "foo(1)": 0, "abs(1, 2)": 0,
    "5 % 0": 2, "8 // (2 - 2)": 2, "1 + sqrt(-4)": 4, "3 # 4": 2, "2 * * 3": 4, "min()": 0,
}
for text, expected in POSITIONS.items():
    try:
        value = evaluate(text)
    except EvalError as err:
        assert err.position == expected, (text, err.position, expected)
    else:
        raise AssertionError((text, value))
