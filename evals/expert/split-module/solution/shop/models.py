"""Reference solution: the shop dataclasses and ShopError.
Product, OrderLine and Order validate themselves and know nothing about files or reports.
This module imports no other shop module.
"""

from dataclasses import dataclass, field


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
