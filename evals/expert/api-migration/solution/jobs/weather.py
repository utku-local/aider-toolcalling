"""Reference solution: Weather jobs for a list of cities.
forecast() uses the client's default timeout and slow_forecast() a generous one.
The client is imported under another name here.
"""

from net import client
from net.client import fetch as get

BASE = "https://weather.example"
SLOW_TIMEOUT = 45


def forecast(city: str) -> dict:
    return get(f"{BASE}/{city}")


def slow_forecast(city: str) -> dict:
    return client.fetch(f"{BASE}/{city}?detail=1", timeout_s=SLOW_TIMEOUT, retries=1)


def bulk(cities: list[str]) -> list[dict]:
    return [get(f"{BASE}/{city}", timeout_s=8) for city in cities]
