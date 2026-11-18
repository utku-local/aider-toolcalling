"""Calendar scheduling package.
It exposes the Event type and the occurrence, conflict and free-slot queries from sched.calendar.
All times are naive datetimes in one time zone.
"""

from sched.calendar import Event, conflicts, free_slots, occurrences

__all__ = ["Event", "conflicts", "free_slots", "occurrences"]
