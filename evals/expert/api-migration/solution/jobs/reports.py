"""Reference solution: Report jobs that share fetch options.
The options travel as a dictionary or are bound with functools.partial.
cached_summary goes through the cache, whose second argument is a maximum age.
"""

import functools

from net.cache import Cache
from net.client import fetch

OPTIONS = {"timeout_s": 4, "retries": 3}
quick_fetch = functools.partial(fetch, timeout_s=2)
REPORTS = "https://reports.example"


def summary() -> dict:
    return fetch(f"{REPORTS}/summary", **OPTIONS)


def quick(name: str) -> dict:
    return quick_fetch(f"{REPORTS}/{name}")


def with_overrides(name: str, **overrides: float) -> dict:
    options = {**OPTIONS, **overrides}
    return fetch(f"{REPORTS}/{name}", timeout_s=options["timeout_s"], retries=options["retries"])


def cached_summary(cache: Cache) -> dict:
    return cache.fetch("summary", 30)


def cached_download(cache: Cache) -> dict:
    return cache.fetch("download", 5)
