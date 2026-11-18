"""Reference solution: runs the shop report from the command line.
`python -m shop FILE` prints the report for a saved order book.
The exit code comes from shop.main.
"""

import sys

from shop import main

sys.exit(main(sys.argv[1:]))
