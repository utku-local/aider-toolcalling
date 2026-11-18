"""Evaluates arithmetic expressions as specified in SPEC.md.
The public interface is evaluate() and EvalError; both are still to be implemented.
No use of eval, exec, compile or the ast module is allowed.
"""

from typing import Optional, Union

Number = Union[int, float]


class EvalError(Exception):
    """An invalid expression; `position` is the 0-based index described in SPEC.md."""

    def __init__(self, message: str, position: int) -> None:
        super().__init__(message)
        self.position = position


def evaluate(expression: str, variables: Optional[dict[str, Number]] = None) -> Number:
    """Return the value of `expression`, looking names up in `variables`."""
    raise NotImplementedError
