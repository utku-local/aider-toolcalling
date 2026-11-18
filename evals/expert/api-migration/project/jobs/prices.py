"""Price feed jobs.
latest() reads the current prices and history() one page per day.
Both use short timeouts because the feed is fast.
"""

from net.client import fetch

FEED = "https://feed.example/prices"


def latest() -> dict:
    return fetch(FEED, 5)


def history(days: int) -> list[dict]:
    return [fetch(f"{FEED}?day={day}", 5, 2) for day in range(days)]
