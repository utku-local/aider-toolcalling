"""Hidden check for the api-migration task.
It checks the new signature of fetch, that Cache.fetch kept its own, and the timeout and retries of every caller.
Exit code 0 means the task passed.
"""

import inspect

from jobs import prices, reports, sync, weather
from net import cache, client

signature = inspect.signature(client.fetch)
assert list(signature.parameters) == ["url", "timeout_s", "retries"], signature
assert signature.parameters["timeout_s"].kind is inspect.Parameter.KEYWORD_ONLY
assert signature.parameters["retries"].kind is inspect.Parameter.KEYWORD_ONLY
assert signature.parameters["timeout_s"].default == 10 and signature.parameters["retries"].default == 0
try:
    client.fetch("u", 5)
except TypeError:
    pass
else:
    raise AssertionError("fetch still accepts a positional timeout")
try:
    client.fetch("u", timeout=5)
except TypeError:
    pass
else:
    raise AssertionError("fetch still accepts timeout=")


def settings(record: dict) -> tuple[float, int]:
    timeouts = [value for key, value in record.items() if key.startswith("timeout")]
    assert len(timeouts) == 1, record
    return timeouts[0], record["retries"]


assert settings(client.fetch("u")) == (10, 0)
assert settings(client.fetch("u", timeout_s=1.5, retries=4)) == (1.5, 4)
assert settings(prices.latest()) == (5, 0)
assert [settings(r) for r in prices.history(2)] == [(5, 2), (5, 2)]
assert settings(weather.forecast("oslo")) == (10, 0)
assert settings(weather.slow_forecast("oslo")) == (45, 1)
assert [settings(r) for r in weather.bulk(["a", "b"])] == [(8, 0), (8, 0)]
assert settings(reports.summary()) == (4, 3)
assert settings(reports.quick("x")) == (2, 0)
assert settings(reports.with_overrides("x")) == (4, 3)
assert settings(reports.with_overrides("x", retries=1)) == (4, 1)
assert [settings(r) for r in sync.run()] == [(3, 0), (12, 2), (30, 2)]

store = cache.Cache()
assert list(inspect.signature(cache.Cache.fetch).parameters) == ["self", "key", "max_age", "loader"]
assert settings(store.fetch("k", 30)) == (2, 1)
assert settings(reports.cached_summary(store)) == (2, 1)
assert settings(reports.cached_download(cache.Cache())) == (2, 1)
assert store.fetch("other", 5, lambda key: {"loaded": key}) == {"loaded": "other"}
