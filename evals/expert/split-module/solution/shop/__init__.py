"""Reference solution: the shop package, re-exporting every public name.
Callers keep importing from `shop`; the code lives in models, storage and reports.
main() is the entry point used by `python -m shop FILE`.
"""

import sys

from shop.models import Order, OrderLine, Product, ShopError
from shop.reports import CURRENCY, TOP_DEFAULT, format_cents, format_report, report_top_products, report_totals
from shop.storage import Storage

__all__ = ["CURRENCY", "TOP_DEFAULT", "Order", "OrderLine", "Product", "ShopError", "Storage", "format_cents",
           "format_report", "main", "report_top_products", "report_totals"]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: shop FILE", file=sys.stderr)
        return 2
    storage = Storage(argv[0])
    try:
        storage.load()
    except ShopError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    print(format_report(storage))
    return 0
