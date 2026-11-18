"""Hidden check for the scheduler task.
It restores and runs the visible tests, then checks the three reported problems and what the docstrings promise.
Exit code 0 means the task passed.
"""

import os
import pathlib
import shutil
import subprocess
import sys
from datetime import datetime

ORIGIN = os.environ.get("EVAL_ORIGIN", "")
if ORIGIN:
    shutil.copy(pathlib.Path(ORIGIN) / "tests" / "test_calendar.py", "tests/test_calendar.py")
tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], capture_output=True)
assert tests.returncode == 0, tests.stderr.decode()

from sched import Event, conflicts, free_slots, occurrences  # noqa: E402


def days(event: Event, start: datetime, end: datetime) -> list[tuple[int, int, int]]:
    return [(s.year, s.month, s.day) for s, _ in occurrences(event, start, end)]


last = Event("report", datetime(2026, 1, 31, 9), datetime(2026, 1, 31, 10), "monthly")
assert days(last, datetime(2026, 1, 1), datetime(2026, 6, 1)) == [
    (2026, 1, 31), (2026, 2, 28), (2026, 3, 31), (2026, 4, 30), (2026, 5, 31)]
leap = Event("leap", datetime(2027, 12, 30, 9), datetime(2027, 12, 30, 10), "monthly")
assert days(leap, datetime(2027, 12, 1), datetime(2028, 4, 1)) == [
    (2027, 12, 30), (2028, 1, 30), (2028, 2, 29), (2028, 3, 30)]
rent = Event("rent", datetime(2026, 11, 15, 8), datetime(2026, 11, 15, 9), "monthly")
assert days(rent, datetime(2027, 1, 1), datetime(2027, 3, 1)) == [(2027, 1, 15), (2027, 2, 15)]


def at(hour: int, minute: int = 0, day: int = 2) -> datetime:
    return datetime(2026, 3, day, hour, minute)


back_to_back = [Event("a", at(9), at(10)), Event("b", at(10), at(11)), Event("c", at(10, 30), at(12))]
assert conflicts(back_to_back, at(0), at(23)) == [("b", "c", at(10, 30))]
daily = [Event("lunch", at(12), at(13), "daily"), Event("review", at(12, 30, 3), at(14, 0, 3))]
assert conflicts(daily, at(0), at(0, 0, 5)) == [("lunch", "review", at(12, 30, 3))]

nested = [Event("workshop", at(9), at(15)), Event("coffee", at(10), at(10, 30)), Event("call", at(14), at(16))]
assert free_slots(nested, at(8), at(18), 30) == [(at(8), at(9)), (at(16), at(18))]
assert free_slots(nested, at(8), at(18), 90) == [(at(16), at(18))]
assert free_slots([], at(8), at(9), 30) == [(at(8), at(9))]
before_day = [Event("early", at(6), at(8, 30))]
assert free_slots(before_day, at(8), at(10), 30) == [(at(8, 30), at(10))]
