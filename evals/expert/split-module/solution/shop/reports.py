"""Reference solution: sales reports over a Storage.
Totals per customer, best-selling products and the printed report.
It depends on shop.storage for the Storage type only.
"""

from shop.storage import Storage

CURRENCY = "EUR"
TOP_DEFAULT = 3


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
