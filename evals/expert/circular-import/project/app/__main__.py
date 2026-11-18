"""Command line entry point for the invoice report.
`python -m app report FILE` reads the invoices from FILE and prints the report.
Any other usage prints a usage line and exits with code 2.
"""

import json
import sys

from app import build_report

USAGE_EXIT = 2

if len(sys.argv) != 3 or sys.argv[1] != "report":
    print("usage: python -m app report FILE", file=sys.stderr)
    sys.exit(USAGE_EXIT)
with open(sys.argv[2]) as handle:
    print(build_report(json.load(handle)))
