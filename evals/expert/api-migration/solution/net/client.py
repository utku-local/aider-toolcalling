"""Reference solution: The HTTP client used by every job.
fetch() is a stand-in that performs no request: it returns a record of how it was called.
That record lets callers and tests see the timeout and retries in effect.
"""

DEFAULT_TIMEOUT = 10
DEFAULT_RETRIES = 0


def fetch(url: str, *, timeout_s: float = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES) -> dict:
    """Request `url`; returns the call record."""
    return {"url": url, "timeout_s": timeout_s, "retries": retries}
