"""Reference solution: the Invoice record used by the report.
An invoice knows its customer, region and net amount, and computes its gross amount with the region's tax.
Records come from JSON, so from_record accepts the raw dictionary.
"""

from dataclasses import dataclass

TAX_RATES = {"eu": 0.20, "uk": 0.20, "us": 0.0}


def tax_for(region: str) -> float:
    return TAX_RATES[region]


@dataclass(frozen=True)
class Invoice:
    customer: str
    region: str
    net: float
    void: bool = False

    @classmethod
    def from_record(cls, record: dict) -> "Invoice":
        return cls(record["customer"], record["region"], float(record["net"]), record.get("void", False))

    def gross(self) -> float:
        return self.net * (1 + tax_for(self.region))
