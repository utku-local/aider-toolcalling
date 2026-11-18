"""An in-memory cache with a loader fallback.
Cache.fetch returns a stored value, or loads, stores and returns it.
Its second argument is a maximum age in seconds, not a network timeout.
"""

from typing import Callable

from net.client import fetch as http_fetch


class Cache:
    def __init__(self) -> None:
        self.values: dict[str, dict] = {}
        self.ages: dict[str, int] = {}

    def fetch(self, key: str, max_age: int = 60, loader: Callable[[str], dict] = None) -> dict:
        """The cached value for `key`, loading it when missing or older than `max_age`."""
        if key not in self.values or self.ages[key] > max_age:
            self.values[key] = (loader or self.download)(key)
            self.ages[key] = 0
        return self.values[key]

    def download(self, key: str) -> dict:
        return http_fetch(f"https://cache.example/{key}", 2, 1)
