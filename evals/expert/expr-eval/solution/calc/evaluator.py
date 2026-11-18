"""Reference solution: a recursive descent evaluator for SPEC.md.
The tokenizer yields (kind, text, position) triples and the parser evaluates while it parses.
Every failure is reported as EvalError with the position the spec names.
"""

import math
import re
from typing import Optional, Union

Number = Union[int, float]
TOKEN = re.compile(r"\s*(?:(\d+\.\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+|\d+)"
                   r"|([A-Za-z_]\w*)|(\*\*|//|[-+*/%(),]))")
END = "end"
ARITY = {"abs": 1, "sqrt": 1}
VARIADIC = {"min": min, "max": max}


class EvalError(Exception):
    """An invalid expression; `position` is the 0-based index described in SPEC.md."""

    def __init__(self, message: str, position: int) -> None:
        super().__init__(message)
        self.position = position


def tokenize(text: str) -> list[tuple[str, str, int]]:
    tokens, index = [], 0
    stripped_end = len(text.rstrip())
    while index < stripped_end:
        match = TOKEN.match(text, index)
        if not match:
            bad = index + len(text[index:]) - len(text[index:].lstrip())
            raise EvalError(f"unexpected character {text[bad]!r}", bad)
        kind = "num" if match.group(1) else "name" if match.group(2) else "op"
        tokens.append((kind, match.group(match.lastindex), match.start(match.lastindex)))
        index = match.end()
    tokens.append((END, "", len(text)))
    return tokens


class Parser:
    def __init__(self, text: str, variables: dict[str, Number]) -> None:
        self.tokens = tokenize(text)
        self.variables = variables
        self.at = 0

    def peek(self) -> tuple[str, str, int]:
        return self.tokens[self.at]

    def take(self, *ops: str) -> Optional[tuple[str, str, int]]:
        kind, text, _ = self.peek()
        if kind == "op" and text in ops:
            self.at += 1
            return self.tokens[self.at - 1]
        return None

    def fail(self) -> EvalError:
        kind, text, position = self.peek()
        return EvalError("unexpected end of input" if kind == END else f"unexpected {text!r}", position)

    def expect(self, op: str) -> None:
        if not self.take(op):
            raise self.fail()

    def sum(self) -> Number:
        value = self.product()
        while token := self.take("+", "-"):
            right = self.product()
            value = value + right if token[1] == "+" else value - right
        return value

    def product(self) -> Number:
        value = self.unary()
        while token := self.take("*", "/", "//", "%"):
            right = self.unary()
            if token[1] != "*" and right == 0:
                raise EvalError("division by zero", token[2])
            value = {"*": lambda: value * right, "/": lambda: value / right,
                     "//": lambda: value // right, "%": lambda: value % right}[token[1]]()
        return value

    def unary(self) -> Number:
        if token := self.take("+", "-"):
            value = self.unary()
            return value if token[1] == "+" else -value
        return self.power()

    def power(self) -> Number:
        base = self.atom()
        if self.take("**"):
            return base ** self.unary()
        return base

    def atom(self) -> Number:
        kind, text, position = self.peek()
        if kind == "num":
            self.at += 1
            return int(text) if text.isdigit() else float(text)
        if kind == "name":
            self.at += 1
            if self.take("("):
                return self.call(text, position)
            if text not in self.variables:
                raise EvalError(f"unknown variable {text}", position)
            return self.variables[text]
        if self.take("("):
            value = self.sum()
            self.expect(")")
            return value
        raise self.fail()

    def call(self, name: str, position: int) -> Number:
        if name not in ARITY and name not in VARIADIC:
            raise EvalError(f"unknown function {name}", position)
        args = []
        if not self.take(")"):
            args.append(self.sum())
            while self.take(","):
                args.append(self.sum())
            self.expect(")")
        if name in VARIADIC:
            if not args:
                raise EvalError(f"{name} needs arguments", position)
            return VARIADIC[name](args)
        if len(args) != ARITY[name]:
            raise EvalError(f"{name} takes one argument", position)
        if name == "abs":
            return abs(args[0])
        if args[0] < 0:
            raise EvalError("sqrt of a negative number", position)
        return math.sqrt(args[0])


def evaluate(expression: str, variables: Optional[dict[str, Number]] = None) -> Number:
    """Return the value of `expression`, looking names up in `variables`."""
    parser = Parser(expression, variables or {})
    value = parser.sum()
    if parser.peek()[0] != END:
        raise parser.fail()
    return value
