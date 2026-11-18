"""Reference solution: recurring calendar events and the queries built on them.
occurrences() expands an event inside a window, conflicts() finds overlapping events and free_slots() finds gaps.
All times are naive datetimes in one time zone, and every interval is half-open: [start, end).
"""

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta

NONE = "none"
DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"
REPEATS = (NONE, DAILY, WEEKLY, MONTHLY)
MONTHS_PER_YEAR = 12
Interval = tuple[datetime, datetime]


class CalendarError(ValueError):
    """An event or query that cannot be valid."""


@dataclass(frozen=True)
class Event:
    title: str
    start: datetime
    end: datetime
    repeat: str = NONE

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise CalendarError(f"{self.title}: end must be after start")
        if self.repeat not in REPEATS:
            raise CalendarError(f"{self.title}: unknown repeat {self.repeat!r}")


def monthly_starts(first: datetime, until: datetime) -> list[datetime]:
    """Starts of a monthly event from `first` up to, not including, `until`.

    The event repeats every month without end, also across years. It falls on the day of the month of `first`,
    or on the last day of a month that is too short for it (Jan 31 -> Feb 28 or 29 -> Mar 31).
    """
    starts = []
    count = 0
    while True:
        index = first.month - 1 + count
        year, month = first.year + index // MONTHS_PER_YEAR, index % MONTHS_PER_YEAR + 1
        day = min(first.day, calendar.monthrange(year, month)[1])
        candidate = first.replace(year=year, month=month, day=day)
        if candidate >= until:
            return starts
        starts.append(candidate)
        count += 1


def stepped_starts(first: datetime, until: datetime, step: timedelta) -> list[datetime]:
    starts = []
    current = first
    while current < until:
        starts.append(current)
        current += step
    return starts


def occurrences(event: Event, window_start: datetime, window_end: datetime) -> list[Interval]:
    """Every occurrence of `event` that overlaps the half-open window, in time order."""
    if window_end <= window_start:
        raise CalendarError("window end must be after window start")
    duration = event.end - event.start
    if event.repeat == NONE:
        starts = [event.start]
    elif event.repeat == MONTHLY:
        starts = monthly_starts(event.start, window_end)
    else:
        step = timedelta(days=1) if event.repeat == DAILY else timedelta(weeks=1)
        starts = stepped_starts(event.start, window_end, step)
    return [(start, start + duration) for start in starts if start < window_end and start + duration > window_start]


def overlap(first: Interval, second: Interval) -> bool:
    """True when two half-open intervals share any time; touching intervals do not overlap."""
    return first[0] < second[1] and second[0] < first[1]


def conflicts(events: list[Event], window_start: datetime, window_end: datetime) -> list[tuple[str, str, datetime]]:
    """Pairs of different events with overlapping occurrences in the window.

    Each entry is (title, other title, start of the overlap), ordered by the overlap start, then by the titles.
    Events are compared in list order, so `title` comes before `other title` in `events`.
    """
    expanded = [(event, occurrences(event, window_start, window_end)) for event in events]
    found = []
    for index, (event, spans) in enumerate(expanded):
        for other, other_spans in expanded[index + 1:]:
            for span in spans:
                for other_span in other_spans:
                    if overlap(span, other_span):
                        found.append((event.title, other.title, max(span[0], other_span[0])))
    return sorted(found, key=lambda entry: (entry[2], entry[0], entry[1]))


def free_slots(events: list[Event], day_start: datetime, day_end: datetime, min_minutes: int) -> list[Interval]:
    """Gaps of at least `min_minutes` between `day_start` and `day_end` in which no event takes place."""
    busy = sorted(span for event in events for span in occurrences(event, day_start, day_end))
    slots = []
    cursor = day_start
    for start, end in busy:
        if start - cursor >= timedelta(minutes=min_minutes):
            slots.append((cursor, start))
        cursor = max(cursor, end)
    if day_end - cursor >= timedelta(minutes=min_minutes):
        slots.append((cursor, day_end))
    return slots
