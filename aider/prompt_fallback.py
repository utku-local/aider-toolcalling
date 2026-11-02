"""Reads one prompt reply, falling back to plain input() when prompt_toolkit cannot use stdin.
On macOS, prompt_toolkit raises OSError (Errno 22) when stdin is /dev/null, because kqueue cannot watch it.
The fallback makes such a run behave like any other end of input: input() raises EOFError and the caller's
existing EOF handling returns the prompt's default answer.
"""

from typing import Callable

PromptCall = Callable[[], str]
LineReader = Callable[[str], str]


def read_reply(prompt_call: PromptCall, question: str, fallback: LineReader = input) -> str:
    """The reply from `prompt_call`; when stdin cannot be watched, the reply read by `fallback` (default: input).

    EOFError from either reader propagates, so callers keep treating end of input as "use the default".
    """
    try:
        return prompt_call()
    except OSError:
        return fallback(question)
