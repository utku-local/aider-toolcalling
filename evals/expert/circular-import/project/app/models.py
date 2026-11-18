"""The Invoice record used by the report.
An invoice knows its customer, region and net amount, and computes its gross amount with the region's tax.
Records come from JSON, so from_record accepts the raw dictionary.
"""

from dataclasses import dataclass

from app.services import tax_for


@dataclass(frozen=True)
class Invoice:
    customer: str
    region: str
    net: float
    void: bool = False

    @classmethod
    def from_record(cls, record: dict) -> "Invoice":
        return cls(record["customer"], record["region"], record["net"], record.get("void", False))

    def gross(self) -> float:
        return self.net * (1 + tax_for(self.region))
