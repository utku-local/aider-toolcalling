"""Command line task list; the behaviour is specified in README.md.
main(argv) parses the arguments, updates the task file and returns the exit code.
Nothing is implemented yet.
"""

import sys


def main(argv: list[str]) -> int:
    """Run one command and return the process exit code."""
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
