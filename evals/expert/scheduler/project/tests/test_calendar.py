"""Tests for sched.calendar covering the simple cases.
They pass on the current code; the reported problems are not covered yet.
Run with: python -m unittest discover -s tests -t .
"""

import unittest
from datetime import datetime

from sched import Event, conflicts, free_slots, occurrences


def at(day: int, hour: int, minute: int = 0, month: int = 3) -> datetime:
    return datetime(2026, month, day, hour, minute)


class CalendarTest(unittest.TestCase):
    def test_weekly(self) -> None:
        event = Event("standup", at(2, 9), at(2, 10), "weekly")
        spans = occurrences(event, at(1, 0), at(20, 0))
        self.assertEqual([s[0].day for s in spans], [2, 9, 16])

    def test_monthly_mid_month(self) -> None:
        event = Event("rent", datetime(2026, 1, 15, 8), datetime(2026, 1, 15, 9), "monthly")
        spans = occurrences(event, datetime(2026, 1, 1), datetime(2026, 4, 1))
        self.assertEqual([(s[0].month, s[0].day) for s in spans], [(1, 15), (2, 15), (3, 15)])

    def test_conflict(self) -> None:
        events = [Event("a", at(2, 9), at(2, 11)), Event("b", at(2, 10), at(2, 12))]
        self.assertEqual(conflicts(events, at(1, 0), at(5, 0)), [("a", "b", at(2, 10))])

    def test_free_slots(self) -> None:
        events = [Event("a", at(2, 9), at(2, 10)), Event("b", at(2, 13), at(2, 14))]
        self.assertEqual(free_slots(events, at(2, 8), at(2, 17), 60),
                         [(at(2, 8), at(2, 9)), (at(2, 10), at(2, 13)), (at(2, 14), at(2, 17))])


if __name__ == "__main__":
    unittest.main()
