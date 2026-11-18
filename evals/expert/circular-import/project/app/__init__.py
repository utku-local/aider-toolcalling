"""Invoice report application.
The package exposes build_report, which turns invoice records into the printed report.
Run it with `python -m app report FILE`.
"""

from app.services import build_report

__all__ = ["build_report"]
