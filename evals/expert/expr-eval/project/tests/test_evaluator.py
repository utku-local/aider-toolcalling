"""Visible tests for calc.evaluator; they cover part of SPEC.md.
The rest of the spec is checked elsewhere, so read SPEC.md as well.
Run with: python -m unittest discover -s tests -t .
"""

import unittest

from calc import EvalError, evaluate


class EvaluatorTest(unittest.TestCase):
    def test_precedence(self) -> None:
        self.assertEqual(evaluate("1 + 2 * 3"), 7)
        self.assertEqual(evaluate("(1 + 2) * 3"), 9)

    def test_types(self) -> None:
        self.assertIsInstance(evaluate("4"), int)
        self.assertIsInstance(evaluate("4.0"), float)
        self.assertEqual(evaluate("7 / 2"), 3.5)
        self.assertEqual(evaluate("7 // 2"), 3)

    def test_power(self) -> None:
        self.assertEqual(evaluate("2 ** 3 ** 2"), 512)
        self.assertEqual(evaluate("-2 ** 2"), -4)

    def test_variables(self) -> None:
        self.assertEqual(evaluate("rate * 2", {"rate": 1.5}), 3.0)

    def test_functions(self) -> None:
        self.assertEqual(evaluate("max(1, 2 + 3, 4)"), 5)
        self.assertEqual(evaluate("abs(-3)"), 3)

    def test_unexpected_character(self) -> None:
        with self.assertRaises(EvalError) as caught:
            evaluate("2 + $")
        self.assertEqual(caught.exception.position, 4)

    def test_division_by_zero(self) -> None:
        with self.assertRaises(EvalError) as caught:
            evaluate("1 / 0")
        self.assertEqual(caught.exception.position, 2)


if __name__ == "__main__":
    unittest.main()
