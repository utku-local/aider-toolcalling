"""A small order book: products, orders, JSON persistence and sales reports.
Everything lives in this one module, which is why it should be split.
Run `python shop.py FILE` to print the report for a saved order book.
"""

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

CURRENCY = "EUR"
TOP_DEFAULT = 3


class ShopError(Exception):
    """An invalid product, order or file."""


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price_cents: int

    def __post_init__(self) -> None:
        if self.price_cents < 0:
            raise ShopError(f"{self.sku}: negative price")


@dataclass(frozen=True)
class OrderLine:
    sku: str
    quantity: int

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ShopError(f"{self.sku}: quantity must be positive")


@dataclass
class Order:
    order_id: int
    customer: str
    lines: list[OrderLine] = field(default_factory=list)

    def add(self, sku: str, quantity: int) -> None:
        self.lines.append(OrderLine(sku, quantity))

    def total_cents(self, catalog: dict[str, Product]) -> int:
        total = 0
        for line in self.lines:
            if line.sku not in catalog:
                raise ShopError(f"order {self.order_id}: unknown product {line.sku}")
            total += catalog[line.sku].price_cents * line.quantity
        return total


class Storage:
    """Keeps products and orders in one JSON file."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.products: dict[str, Product] = {}
        self.orders: list[Order] = []

    def add_product(self, product: Product) -> None:
        if product.sku in self.products:
            raise ShopError(f"duplicate product {product.sku}")
        self.products[product.sku] = product

    def new_order(self, customer: str) -> Order:
        order = Order(len(self.orders) + 1, customer)
        self.orders.append(order)
        return order

    def save(self) -> None:
        data = {
            "products": [asdict(product) for product in self.products.values()],
            "orders": [asdict(order) for order in self.orders],
        }
        self.path.write_text(json.dumps(data, indent=2))

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as err:
            raise ShopError(f"cannot read {self.path}: {err}") from err
        self.products = {item["sku"]: Product(**item) for item in data["products"]}
        self.orders = [
            Order(item["order_id"], item["customer"], [OrderLine(**line) for line in item["lines"]])
            for item in data["orders"]
        ]


def format_cents(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d} {CURRENCY}"


def report_totals(storage: Storage) -> dict[str, int]:
    """Total spent per customer in cents, customers in order of first appearance."""
    totals: dict[str, int] = {}
    for order in storage.orders:
        totals[order.customer] = totals.get(order.customer, 0) + order.total_cents(storage.products)
    return totals


def report_top_products(storage: Storage, count: int = TOP_DEFAULT) -> list[tuple[str, int]]:
    """The `count` best-selling products as (name, units), most units first, ties by name."""
    units: dict[str, int] = {}
    for order in storage.orders:
        for line in order.lines:
            units[line.sku] = units.get(line.sku, 0) + line.quantity
    named = [(storage.products[sku].name, sold) for sku, sold in units.items()]
    return sorted(named, key=lambda item: (-item[1], item[0]))[:count]


def format_report(storage: Storage) -> str:
    lines = ["Customers"]
    lines += [f"  {customer}: {format_cents(total)}" for customer, total in report_totals(storage).items()]
    lines.append("Top products")
    lines += [f"  {name} x{units}" for name, units in report_top_products(storage)]
    return "\n".join(lines)


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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
