"""Tests for the shop order book through its public names.
They import everything from the top-level `shop`, as callers do.
Run with: python -m unittest discover -s tests -t .
"""

import tempfile
import unittest
from pathlib import Path

from shop import Order, Product, ShopError, Storage, format_report, report_top_products, report_totals


def sample(path: str) -> Storage:
    storage = Storage(path)
    storage.add_product(Product("p1", "Pen", 150))
    storage.add_product(Product("n1", "Notebook", 499))
    storage.new_order("ada").add("p1", 4)
    second = storage.new_order("bob")
    second.add("n1", 1)
    second.add("p1", 1)
    storage.new_order("ada").add("n1", 2)
    return storage


class ShopTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = str(Path(tempfile.mkdtemp()) / "shop.json")

    def test_totals(self) -> None:
        self.assertEqual(report_totals(sample(self.path)), {"ada": 1598, "bob": 649})

    def test_round_trip(self) -> None:
        sample(self.path).save()
        loaded = Storage(self.path)
        loaded.load()
        self.assertIsInstance(loaded.orders[0], Order)
        self.assertEqual(report_top_products(loaded, 1), [("Pen", 5)])
        self.assertIn("  ada: 15.98 EUR", format_report(loaded))

    def test_errors(self) -> None:
        with self.assertRaises(ShopError):
            Product("x", "X", -1)
        with self.assertRaises(ShopError):
            Storage(self.path).load()


if __name__ == "__main__":
    unittest.main()
