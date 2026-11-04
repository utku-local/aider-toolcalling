"""Turns a reasoning model's thinking trace on or off by setting the chat-template flag the mlx_lm server reads.
The flag lives at extra_params["extra_body"]["chat_template_kwargs"]["enable_thinking"], which Model.send_completion
merges into every request, so flipping it applies on the next request with no server restart.
Pure dictionary surgery: callers persist the choice and do any file I/O themselves.
"""

from typing import Any, Optional

EXTRA_BODY = "extra_body"
CHAT_TEMPLATE_KWARGS = "chat_template_kwargs"
ENABLE_THINKING = "enable_thinking"


def with_thinking(extra_params: Optional[dict[str, Any]], enabled: Optional[bool]) -> Optional[dict[str, Any]]:
    """Copy of `extra_params` with the thinking flag set to `enabled`; unchanged when `enabled` is None."""
    if enabled is None:
        return extra_params
    params = {**(extra_params or {})}
    body = {**(params.get(EXTRA_BODY) or {})}
    kwargs = {**(body.get(CHAT_TEMPLATE_KWARGS) or {})}
    kwargs[ENABLE_THINKING] = enabled
    body[CHAT_TEMPLATE_KWARGS] = kwargs
    params[EXTRA_BODY] = body
    return params


def thinking_enabled(extra_params: Optional[dict[str, Any]]) -> bool:
    """Whether the thinking flag is currently set on `extra_params` (default False when unset)."""
    if not extra_params:
        return False
    body = extra_params.get(EXTRA_BODY) or {}
    kwargs = body.get(CHAT_TEMPLATE_KWARGS) or {}
    return bool(kwargs.get(ENABLE_THINKING, False))
