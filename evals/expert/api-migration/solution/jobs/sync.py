"""Reference solution: The nightly sync job.
It walks a table of endpoints, each with its own timeout, and retries the slow ones.
run() returns every fetch record in table order.
"""

from net.client import fetch

ENDPOINTS = (("users", 3), ("orders", 12), ("stock", 30))
SLOW_AFTER = 10
SLOW_RETRIES = 2


def run() -> list[dict]:
    records = []
    for name, timeout in ENDPOINTS:
        url = f"https://sync.example/{name}"
        if timeout > SLOW_AFTER:
            records.append(fetch(url, timeout_s=timeout, retries=SLOW_RETRIES))
        else:
            records.append(fetch(url, timeout_s=timeout))
    return records
