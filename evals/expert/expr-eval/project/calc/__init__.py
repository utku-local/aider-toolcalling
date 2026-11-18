"""Arithmetic expression evaluator package.
It exposes evaluate and EvalError from calc.evaluator.
The behaviour is specified in SPEC.md at the project root.
"""

from calc.evaluator import EvalError, evaluate

__all__ = ["EvalError", "evaluate"]
