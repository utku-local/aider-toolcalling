"""Reference solution: JSON persistence for the shop order book.
Storage keeps products and orders in memory and saves or loads them as one file.
It depends only on shop.models.
"""

import json
from dataclasses import asdict
from pathlib import Path

from shop.models import Order, OrderLine, Product, ShopError


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
