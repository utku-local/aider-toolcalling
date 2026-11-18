# Expression evaluator

`evaluate(expression, variables=None)` returns the numeric value of an arithmetic expression.

## Syntax

- Numbers: `12`, `3.5`, `.5`, `1e3`, `2.5e-2`. A number without `.` or an exponent is an `int`, otherwise a `float`.
- Binary operators, lowest precedence first:
  1. `+` `-`
  2. `*` `/` `//` `%`
  3. unary `+` `-`
  4. `**` (right associative)
- So `-2 ** 2` is `-4`, `2 ** 3 ** 2` is `512` and `2 ** -1` is `0.5`.
- Parentheses group as usual. Whitespace between tokens is ignored.
- Variables are identifiers (`[A-Za-z_][A-Za-z0-9_]*`) looked up in `variables`.
- Functions: `min(a, b, ...)` and `max(a, b, ...)` take one or more arguments, `abs(x)` and `sqrt(x)` take one.
  An identifier directly followed by `(` (whitespace allowed) is a function call.
- Arithmetic follows Python: `7 / 2` is `3.5`, `7 // 2` is `3`, `-7 % 3` is `2`.

## Errors

Every problem raises `EvalError(message, position)`; no other exception may escape. `position` is the 0-based
index into `expression`:

| Problem | Position | Example |
|---|---|---|
| Unexpected character | that character | `2 + $` -> 4 |
| Unexpected end of input | `len(expression)` | `(1 + 2` -> 6, empty string -> 0 |
| Unexpected token (also trailing input) | start of that token | `1 2` -> 2, `(1))` -> 3 |
| Unknown variable | start of the name | `1 + foo` -> 4 |
| Unknown function | start of the name | `foo(1)` -> 0 |
| Wrong number of arguments | start of the function name | `abs(1, 2)` -> 0 |
| Division or modulo by zero (`/`, `//`, `%`) | the operator | `1 / 0` -> 2 |
| `sqrt` of a negative number | start of the function name | `1 + sqrt(-4)` -> 4 |
