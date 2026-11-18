"""Reference solution: the invoice report.
tax_for gives the tax rate of a region and build_report formats the totals per customer.
The report format is described in README.md.
"""

from app.models import Invoice, tax_for

NAME_WIDTH = 10
AMOUNT_WIDTH = 10


def totals_by_customer(invoices: list[Invoice]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for invoice in invoices:
        if invoice.void:
            continue
        name = invoice.customer.lower()
        totals[name] = totals.get(name, 0) + invoice.gross()
    return totals


def build_report(records: list[dict]) -> str:
    """The report text for raw invoice records."""
    invoices = [Invoice.from_record(record) for record in records]
    totals = totals_by_customer(invoices)
    lines = [f"{name:<{NAME_WIDTH}}{amount:>{AMOUNT_WIDTH},.2f}"
             for name, amount in sorted(totals.items(), key=lambda item: (-item[1], item[0]))]
    lines.append(f"{'TOTAL':<{NAME_WIDTH}}{sum(totals.values()):>{AMOUNT_WIDTH},.2f}")
    return "\n".join(lines)
