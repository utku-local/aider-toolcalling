"""Decides what the agent does when a model request times out, and how long it waits before that.
A local server such as mlx_lm cannot cancel a request the client has given up on: it finishes the abandoned
generation first, so a retry only queues the same work again behind it. Measured on the 27B: after one timeout the
server spent about 20 minutes on abandoned generations and the next task received no reply at all.
So the agent waits longer than upstream's 600 seconds and never re-sends a request that timed out.
"""

# Longer than the slowest full reply seen: 8,192 tokens at about 12 tokens per second is roughly 11 minutes, and
# 16,384 tokens on the faster model about the same; upstream's 600 seconds cut both off just before the end.
AGENT_REQUEST_TIMEOUT_SECONDS = 1800
TIMEOUT_ERROR_NAME = "Timeout"
AGENT_EDIT_FORMAT = "agent"
TIMEOUT_TEXT = "timed out"
TIMEOUT_STOP = (
    "The model server did not answer in time. The request is not sent again: a local server keeps generating a "
    "request the client gave up on, and a retry would queue the same work behind it. Your work so far is kept; "
    "wait for the server to go idle (or restart it), then continue with a new message."
)


def is_timeout(error_name: str, message: str) -> bool:
    """True for litellm's Timeout and for connection errors that report a timeout in their text."""
    return error_name == TIMEOUT_ERROR_NAME or TIMEOUT_TEXT in message.lower()


def agent_timeout(requested: float | None, agent: bool) -> float | None:
    """The request timeout to use: the user's --timeout when given, the agent default in agent mode, else None
    (None keeps upstream's default)."""
    if requested:
        return requested
    return AGENT_REQUEST_TIMEOUT_SECONDS if agent else None
