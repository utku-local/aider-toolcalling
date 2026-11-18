"""Tax rates and the invoice report.
tax_for gives the tax rate of a region and build_report formats the totals per customer.
The report format is described in README.md.
"""

from app.models import Invoice

TAX_RATES = {"eu": 0.20, "uk": 0.20, "us": 0.0}
NAME_WIDTH = 10
AMOUNT_WIDTH = 10


def tax_for(region: str) -> float:
    return TAX_RATES[region]


def totals_by_customer(invoices: list[Invoice]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for invoice in invoices:
        totals[invoice.customer] = totals.get(invoice.customer, 0) + invoice.gross()
    return totals


def build_report(records: list[dict]) -> str:
    """The report text for raw invoice records."""
    invoices = [Invoice.from_record(record) for record in records]
    totals = totals_by_customer(invoices)
    lines = [f"{name:<{NAME_WIDTH}}{amount:>{AMOUNT_WIDTH}.2f}" for name, amount in sorted(totals.items())]
    lines.append(f"{'TOTAL':<{NAME_WIDTH}}{sum(totals.values()):>{AMOUNT_WIDTH}.2f}")
    return "\n".join(lines)
